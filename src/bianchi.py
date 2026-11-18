from scipy.optimize import brentq
from config import DCFConfig


def solve_bianchi(cfg: DCFConfig) -> dict:
    """
    Giải mô hình giải tích Bianchi (2000) cho mạng bão hòa, không nút ẩn.
    Trả về tau, p_collision và throughput_mbps.
    """
    n = cfg.n_stations
    w = cfg.cw_min
    m = cfg.backoff_stages

    if n == 1:
        # Trường hợp 1 trạm: không có va chạm (p = 0), backoff trung bình = (W - 1) / 2
        p = 0.0
        tau = 2.0 / (w + 1.0)
    else:
        def tau_from_p(p_val: float) -> float:
            # Xử lý giới hạn khi 2p -> 1 để tránh chia cho 0
            if abs(1.0 - 2.0 * p_val) < 1e-9:
                denom = w * (1.0 + m / 2.0) + 1.0
                return 2.0 / denom
            num = 2.0 * (1.0 - 2.0 * p_val)
            denom = (1.0 - 2.0 * p_val) * (w + 1.0) + p_val * w * (1.0 - (2.0 * p_val) ** m)
            return num / denom

        def objective(p_val: float) -> float:
            tau_val = tau_from_p(p_val)
            return p_val - (1.0 - (1.0 - tau_val) ** (n - 1))

        p = brentq(objective, 1e-12, 1.0 - 1e-12)
        tau = tau_from_p(p)

    # Xác suất có ít nhất 1 trạm phát trong một slot
    p_tr = 1.0 - (1.0 - tau) ** n
    # Xác suất truyền thành công có điều kiện
    p_s = (n * tau * ((1.0 - tau) ** (n - 1))) / p_tr if p_tr > 0 else 0.0

    # Thời gian truyền gói & thời gian chu kỳ thành công / va chạm (bao gồm DIFS sau khi kênh rảnh)
    t_payload = cfg.payload_bits / cfg.bit_rate
    t_s = cfg.t_success_busy + cfg.difs
    t_c = cfg.t_collision_busy + cfg.difs
    sigma = cfg.slot_time

    expected_slot_duration = (1.0 - p_tr) * sigma + p_tr * p_s * t_s + p_tr * (1.0 - p_s) * t_c
    normalized_throughput = (p_tr * p_s * t_payload) / expected_slot_duration
    throughput_mbps = normalized_throughput * (cfg.bit_rate / 1e6)

    return {
        "tau": tau,
        "p_collision": p,
        "throughput_mbps": throughput_mbps,
    }