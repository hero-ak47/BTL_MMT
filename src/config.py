from dataclasses import dataclass

@dataclass
class DCFConfig:
    # --- Tham số lớp vật lý & MAC cố định (IEEE 802.11 DSSS 1 Mbps - Bianchi 2000) ---
    bit_rate: float = 1e6          # 1 Mbps (bits/s)
    slot_time: float = 50e-6       # 50 us
    sifs: float = 28e-6            # 28 us
    prop_delay: float = 1e-6       # 1 us (trễ lan truyền)

    phy_header_bits: int = 128     # bits
    mac_header_bits: int = 272     # bits
    payload_bits: int = 8184       # 1023 bytes = 8184 bits
    ack_bits: int = 112 + 128      # 112 bits ACK + 128 bits PHY header = 240 bits

    cw_min: int = 32               # W0 (bốc backoff trong [0, CW - 1])
    backoff_stages: int = 5        # m: CW_max = 2^m * CW_min = 1024
    retry_limit: int = 7           # Giới hạn truyền lại tối đa

    # --- Tham số kịch bản thí nghiệm ---
    n_stations: int = 10
    saturated: bool = True         # True: luôn có gói để phát; False: phát sinh Poisson
    arrival_rate: float = 10.0     # Gói/giây mỗi trạm (chỉ dùng khi saturated=False)
    queue_capacity: int = 1000     # Kích thước hàng đợi mỗi trạm
    sim_time: float = 20.0         # Tổng thời gian mô phỏng (giây)
    warmup_time: float = 2.0       # Thời gian khởi động bỏ qua khi đo (giây)
    seed: int = 42

    @property
    def difs(self) -> float:
        return self.sifs + 2 * self.slot_time  # 128 us

    @property
    def cw_max(self) -> int:
        return self.cw_min * (2 ** self.backoff_stages)

    @property
    def t_data(self) -> float:
        total_bits = self.phy_header_bits + self.mac_header_bits + self.payload_bits
        return total_bits / self.bit_rate

    @property
    def t_ack(self) -> float:
        return self.ack_bits / self.bit_rate

    @property
    def t_success_busy(self) -> float:
        # Thời gian kênh bận cho một lần truyền thành công: DATA + prop + SIFS + ACK + prop
        return self.t_data + self.prop_delay + self.sifs + self.t_ack + self.prop_delay

    @property
    def t_collision_busy(self) -> float:
        # Thời gian kênh bận khi va chạm (hết thời gian chờ ACK / EIFS trước DIFS)
        return self.t_data + self.prop_delay + self.sifs + self.t_ack + self.prop_delay