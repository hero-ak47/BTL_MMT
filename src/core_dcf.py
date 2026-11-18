import random
from dataclasses import dataclass
from typing import List, Optional
import simpy
from config import DCFConfig


@dataclass
class Packet:
    pkt_id: int
    src_id: int
    arrival_time: float
    retry_count: int = 0


class WirelessChannel:
    """Kênh vô tuyến dùng chung trong một miền va chạm (không nút ẩn)."""

    def __init__(self, env: simpy.Environment, cfg: DCFConfig):
        self.env = env
        self.cfg = cfg
        self.is_busy: bool = False
        self.last_idle_time: float = 0.0

        self.tx_started_event: simpy.Event = env.event()
        self.idle_event: simpy.Event = env.event()

        self.pending_tx: list = []
        self.arbiter_scheduled: bool = False

        # Thống kê cấp độ kênh (sau warmup)
        self.total_tx_attempts: int = 0
        self.collided_tx_attempts: int = 0

    def transmit(self, station: "Station", packet: Packet):
        """Trạm đăng ký phát tại thời điểm hiện tại; trả về True nếu nhận được ACK."""
        done_ev = self.env.event()
        self.pending_tx.append((station, packet, done_ev))
        if not self.arbiter_scheduled:
            self.arbiter_scheduled = True
            self.env.process(self._resolve_transmission())
        return done_ev

    def _resolve_transmission(self):
        # Đợi hết tất cả sự kiện cùng timestamp hiện tại để gom đủ các trạm cùng phát
        yield self.env.timeout(0)

        batch = list(self.pending_tx)
        self.pending_tx.clear()
        self.arbiter_scheduled = False

        # Kênh chuyển sang bận -> ngắt các trạm đang đếm DIFS hoặc slot backoff
        self.is_busy = True
        tx_ev = self.tx_started_event
        self.tx_started_event = self.env.event()
        tx_ev.succeed()

        is_success = (len(batch) == 1)
        if self.env.now >= self.cfg.warmup_time:
            self.total_tx_attempts += len(batch)
            if not is_success:
                self.collided_tx_attempts += len(batch)

        busy_duration = self.cfg.t_success_busy if is_success else self.cfg.t_collision_busy
        yield self.env.timeout(busy_duration)

        # Kênh rảnh trở lại
        self.is_busy = False
        self.last_idle_time = self.env.now
        id_ev = self.idle_event
        self.idle_event = self.env.event()
        id_ev.succeed()

        for _, _, done_ev in batch:
            done_ev.succeed(value=is_success)


class Station:
    """Trạm phát chuẩn IEEE 802.11 DCF (Basic Access)."""

    def __init__(self, env: simpy.Environment, station_id: int, cfg: DCFConfig,
                 channel: WirelessChannel, rng: random.Random):
        self.env = env
        self.station_id = station_id
        self.cfg = cfg
        self.channel = channel
        self.rng = rng

        self.queue: List[Packet] = []
        self.pkt_seq: int = 0
        self.pkt_arrived_event: simpy.Event = env.event()

        self.cw: int = cfg.cw_min
        self.backoff_counter: Optional[int] = None

        # Chỉ tiêu đo lường (chỉ ghi nhận sau warmup_time)
        self.packets_generated: int = 0
        self.packets_acked: int = 0
        self.packets_dropped: int = 0
        self.delivered_bits: int = 0
        self.delays: List[float] = []
        self.tx_count: int = 0
        self.retry_tx_count: int = 0

        if not cfg.saturated:
            self.env.process(self._traffic_generator())
        self.env.process(self._mac_loop())

    def _enqueue_packet(self):
        self.pkt_seq += 1
        if self.env.now >= self.cfg.warmup_time:
            self.packets_generated += 1

        if len(self.queue) < self.cfg.queue_capacity:
            pkt = Packet(pkt_id=self.pkt_seq, src_id=self.station_id, arrival_time=self.env.now)
            self.queue.append(pkt)
            if len(self.queue) == 1:
                ev = self.pkt_arrived_event
                self.pkt_arrived_event = self.env.event()
                ev.succeed()
        else:
            if self.env.now >= self.cfg.warmup_time:
                self.packets_dropped += 1

    def _traffic_generator(self):
        while True:
            inter_arrival = self.rng.expovariate(self.cfg.arrival_rate)
            yield self.env.timeout(inter_arrival)
            self._enqueue_packet()

    def _wait_difs(self):
        """Chờ kênh rảnh liên tục đủ khoảng DIFS."""
        while True:
            if self.channel.is_busy:
                yield self.channel.idle_event
                continue
            idle_elapsed = self.env.now - self.channel.last_idle_time
            if idle_elapsed >= self.cfg.difs - 1e-12:
                return
            rem_difs = self.cfg.difs - idle_elapsed
            tx_ev = self.channel.tx_started_event
            res = yield self.env.timeout(rem_difs) | tx_ev
            if tx_ev not in res:
                return

    def _mac_loop(self):
        if self.cfg.saturated:
            self._enqueue_packet()

        while True:
            if not self.queue:
                yield self.pkt_arrived_event
                continue

            pkt = self.queue[0]

            # Khởi tạo backoff cho gói mới nếu chưa có
            if self.backoff_counter is None:
                idle_elapsed = self.env.now - self.channel.last_idle_time
                # Nếu kênh đã rảnh >= DIFS khi gói mới đến hàng đợi rỗng -> phát ngay (backoff = 0)
                if not self.channel.is_busy and idle_elapsed >= self.cfg.difs - 1e-12 and pkt.retry_count == 0:
                    self.backoff_counter = 0
                else:
                    self.backoff_counter = self.rng.randint(0, self.cw - 1)

            # Vòng lặp tranh chấp: DIFS -> đếm lùi từng slot (đóng băng nếu kênh bận)
            while True:
                yield self.env.process(self._wait_difs())

                interrupted = False
                while self.backoff_counter > 0:
                    tx_ev = self.channel.tx_started_event
                    res = yield self.env.timeout(self.cfg.slot_time) | tx_ev
                    if tx_ev in res:
                        # Kênh bận -> đóng băng backoff_counter
                        interrupted = True
                        break
                    self.backoff_counter -= 1

                if not interrupted and self.backoff_counter == 0:
                    break

            # Phát khung dữ liệu và chờ kết quả ACK
            if self.env.now >= self.cfg.warmup_time:
                self.tx_count += 1
                if pkt.retry_count > 0:
                    self.retry_tx_count += 1

            success = yield self.channel.transmit(self, pkt)

            if success:
                self.queue.pop(0)
                self.cw = self.cfg.cw_min
                self.backoff_counter = None
                if self.env.now >= self.cfg.warmup_time:
                    self.packets_acked += 1
                    self.delivered_bits += self.cfg.payload_bits
                    self.delays.append(self.env.now - pkt.arrival_time)
                if self.cfg.saturated:
                    self._enqueue_packet()
            else:
                pkt.retry_count += 1
                if pkt.retry_count > self.cfg.retry_limit:
                    # Vượt quá giới hạn thử lại -> hủy gói
                    self.queue.pop(0)
                    self.cw = self.cfg.cw_min
                    self.backoff_counter = None
                    if self.env.now >= self.cfg.warmup_time:
                        self.packets_dropped += 1
                    if self.cfg.saturated:
                        self._enqueue_packet()
                else:
                    # Nhân đôi CW (tối đa CW_max) và bốc lại backoff
                    self.cw = min(self.cw * 2, self.cfg.cw_max)
                    self.backoff_counter = self.rng.randint(0, self.cw - 1)


def run_simulation(cfg: DCFConfig) -> dict:
    """Chạy một lượt mô phỏng và trả về 5 chỉ tiêu đánh giá."""
    rng = random.Random(cfg.seed)
    env = simpy.Environment()
    channel = WirelessChannel(env, cfg)
    stations = [Station(env, i, cfg, channel, rng) for i in range(cfg.n_stations)]

    env.run(until=cfg.sim_time)

    measure_duration = cfg.sim_time - cfg.warmup_time
    per_station_tp = [st.delivered_bits / (measure_duration * 1e6) for st in stations]  # Mbps

    total_tp = sum(per_station_tp)
    total_gen = sum(st.packets_generated for st in stations)
    total_acked = sum(st.packets_acked for st in stations)
    all_delays = [d for st in stations for d in st.delays]
    total_tx = sum(st.tx_count for st in stations)
    total_retry_tx = sum(st.retry_tx_count for st in stations)

    # Chỉ số công bằng Jain
    sum_x = sum(per_station_tp)
    sum_x2 = sum(x * x for x in per_station_tp)
    jain_fairness = (sum_x ** 2) / (cfg.n_stations * sum_x2) if sum_x2 > 0 else 1.0

    p_collision = (
        channel.collided_tx_attempts / channel.total_tx_attempts
        if channel.total_tx_attempts > 0 else 0.0
    )

    return {
        "throughput_mbps": total_tp,
        "pdr": total_acked / total_gen if total_gen > 0 else 0.0,
        "avg_delay_ms": (sum(all_delays) / len(all_delays) * 1e3) if all_delays else 0.0,
        "retry_rate": total_retry_tx / total_tx if total_tx > 0 else 0.0,
        "fairness": jain_fairness,
        "collision_prob": p_collision,
    }