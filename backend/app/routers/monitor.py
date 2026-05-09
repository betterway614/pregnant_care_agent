"""硬件资源监控 API (Mock)"""
import random
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/monitor", tags=["硬件监控"])


@router.get("/hardware")
def get_hardware_monitor():
    """获取AMD硬件资源实时监控数据 (Mock)"""
    return {
        "gpu_utilization": round(random.uniform(45, 85), 1),
        "gpu_memory_used": round(random.uniform(20, 50), 1),
        "npu_utilization": round(random.uniform(30, 70), 1),
        "cpu_utilization": round(random.uniform(25, 55), 1),
        "memory_used": round(random.uniform(40, 80), 1),
        "memory_total": 128,
        "inference_latency_ms": round(random.uniform(800, 2500), 0),
        "power_watts": round(random.uniform(65, 110), 1),
        "gpu_info": {
            "model": "AMD Radeon 8060S",
            "driver": "ROCm 6.2",
            "temperature": round(random.uniform(55, 75), 1),
        },
        "npu_info": {
            "model": "AMD Ryzen AI NPU",
            "status": "active",
            "ops": "16 TOPS",
        },
        "uma_info": {
            "total_gb": 128,
            "used_gb": round(random.uniform(40, 80), 1),
            "available_gb": round(random.uniform(48, 88), 1),
        },
        "timestamp": __import__('datetime').datetime.now().isoformat(),
    }
