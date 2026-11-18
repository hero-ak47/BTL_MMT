import numpy as np
from config import DCFConfig
from core_dcf import run_simulation
from bianchi import solve_bianchi


def evaluate_multi_seed(base_cfg: DCFConfig, seeds=(10, 20, 30, 40, 50)) -> dict:
    runs = []
    for s in seeds:
        cfg = DCFConfig(**{**base_cfg.__dict__, "seed": s})
        runs.append(run_simulation(cfg))

    summary = {}
    for key in runs[0].keys():
        vals = [r[key] for r in runs]
        summary[key] = (float(np.mean(vals)), float(np.std(vals, ddof=1)))
    return summary


if __name__ == "__main__":
    seeds = [101, 202, 303, 404, 505]  # 5 seed độc lập

    print("=== KỊCH BẢN 1: ĐỐI CHIẾU MÔ PHỎNG BÃO HÒA VỚI BIANCHI THEO SỐ TRẠM N ===")
    header = f"{'N':>3} | {'Sim TP (Mbps)':>17} | {'Bianchi TP':>10} | {'Sim p_col':>14} | {'Bianchi p':>9} | {'Delay (ms)':>10} | {'Fairness':>8}"
    print(header)
    print("-" * len(header))

    for n in [1, 2, 5, 10, 20, 30]:
        cfg = DCFConfig(n_stations=n, cw_min=32, backoff_stages=5, saturated=True, sim_time=15.0, warmup_time=1.5)
        sim_res = evaluate_multi_seed(cfg, seeds)
        ana_res = solve_bianchi(cfg)

        tp_m, tp_s = sim_res["throughput_mbps"]
        pc_m, pc_s = sim_res["collision_prob"]
        dl_m, _ = sim_res["avg_delay_ms"]
        fr_m, _ = sim_res["fairness"]

        print(
            f"{n:>3} | {tp_m:>7.4f} ± {tp_s:<7.4f} | {ana_res['throughput_mbps']:>10.4f} | "
            f"{pc_m:>6.3f} ± {pc_s:<5.3f} | {ana_res['p_collision']:>9.3f} | "
            f"{dl_m:>10.2f} | {fr_m:>8.4f}"
        )

    print("\n=== KỊCH BẢN 2: KHẢO SÁT CỬA SỔ TRANH CHẤP CW_MIN (BÃO HÒA) ===")
    cw_list = [8, 16, 32, 64, 128]  # Tương ứng bốc backoff trong [0, 7] .. [0, 127]

    for n in [5, 30]:
        print(f"\n--- Mật độ trạm N = {n} ---")
        header_cw = (
            f"{'CW_min':>6} | {'Sim TP (Mbps)':>17} | {'Bianchi TP':>10} | "
            f"{'Sim p_col':>14} | {'Bianchi p':>9} | {'Delay (ms)':>10} | {'Retry':>6}"
        )
        print(header_cw)
        print("-" * len(header_cw))

        for cw in cw_list:
            cfg = DCFConfig(
                n_stations=n,
                cw_min=cw,
                backoff_stages=5,
                saturated=True,
                sim_time=15.0,
                warmup_time=1.5,
            )
            sim_res = evaluate_multi_seed(cfg, seeds)
            ana_res = solve_bianchi(cfg)

            tp_m, tp_s = sim_res["throughput_mbps"]
            pc_m, pc_s = sim_res["collision_prob"]
            dl_m, _ = sim_res["avg_delay_ms"]
            rt_m, _ = sim_res["retry_rate"]

            print(
                f"{cw:>6} | {tp_m:>7.4f} ± {tp_s:<7.4f} | {ana_res['throughput_mbps']:>10.4f} | "
                f"{pc_m:>6.3f} ± {pc_s:<5.3f} | {ana_res['p_collision']:>9.3f} | "
                f"{dl_m:>10.2f} | {rt_m:>6.3f}"
            )

    print("\n=== KỊCH BẢN 3: KHẢO SÁT MỨC TẢI LƯU LƯỢNG (N = 10, KHÔNG BÃO HÒA) ===")
    for lam in [2.0, 5.0, 8.0, 12.0, 20.0]:
        cfg = DCFConfig(n_stations=10, saturated=False, arrival_rate=lam, sim_time=15.0, warmup_time=1.5)
        sim_res = evaluate_multi_seed(cfg, seeds)
        tp_m, tp_s = sim_res["throughput_mbps"]
        pdr_m, _ = sim_res["pdr"]
        dl_m, dl_s = sim_res["avg_delay_ms"]
        rt_m, _ = sim_res["retry_rate"]
        print(f"Lambda={lam:>4.1f} pkt/s | TP={tp_m:.4f}±{tp_s:.4f} Mbps | PDR={pdr_m:.3f} | Delay={dl_m:.2f}±{dl_s:.2f} ms | Retry={rt_m:.3f}")