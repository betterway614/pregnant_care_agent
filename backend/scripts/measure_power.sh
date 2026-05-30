#!/bin/bash
# AI-Care 功耗测量脚本
# 用法: bash scripts/measure_power.sh [duration_seconds]
# 需要在AMD Ryzen AI Max+硬件上运行

DURATION=${1:-60}
LOG_DIR="$(dirname "$0")/../../docs/benchmark_logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/power_measurement.txt"

echo "=== AI-Care 功耗测量 ===" | tee "$LOG_FILE"
echo "时间: $(date)" | tee -a "$LOG_FILE"
echo "测量时长: ${DURATION}s" | tee -a "$LOG_FILE"
echo "---" | tee -a "$LOG_FILE"

# 方法1: AMD ROCm
if command -v rocm-smi &> /dev/null; then
    echo "使用 rocm-smi 测量..." | tee -a "$LOG_FILE"
    timeout "$DURATION" rocm-smi --showpower --showtemp --csv >> "$LOG_FILE" 2>&1
    echo "rocm-smi 数据已记录到 $LOG_FILE"

# 方法2: Intel/AMD RAPL
elif [ -f /sys/class/powercap/intel-rapl:0/energy_uj ]; then
    echo "使用 RAPL 测量..." | tee -a "$LOG_FILE"
    E1=$(cat /sys/class/powercap/intel-rapl:0/energy_uj)
    sleep "$DURATION"
    E2=$(cat /sys/class/powercap/intel-rapl:0/energy_uj)
    DIFF=$(( (E2 - E1) / 1000000 ))
    AVG_POWER=$(( DIFF / DURATION ))
    echo "平均功耗: ${AVG_POWER}W (${DURATION}秒)" | tee -a "$LOG_FILE"

# 方法3: 笔记本电池
elif [ -f /sys/class/power_supply/BAT0/power_now ]; then
    echo "使用电池传感器测量..." | tee -a "$LOG_FILE"
    for i in $(seq 1 "$DURATION"); do
        POWER=$(cat /sys/class/power_supply/BAT0/power_now 2>/dev/null)
        echo "$(date +%H:%M:%S) $((POWER/1000000))W" | tee -a "$LOG_FILE"
        sleep 1
    done

else
    echo "未找到功耗测量接口" | tee -a "$LOG_FILE"
    echo "请使用外部功率计或安装 rocm-smi" | tee -a "$LOG_FILE"
fi

echo "---" | tee -a "$LOG_FILE"
echo "结果: $LOG_FILE"
