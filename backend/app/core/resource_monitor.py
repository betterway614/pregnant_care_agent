"""
资源监控器 - 实时监控系统资源状态 (VRAM, GPU, CPU, NPU)

用于动态资源管理，提供实时资源使用数据。
"""

import os
import time
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class LoadLevel(str, Enum):
    """系统负载级别"""
    LOW = "low"           # < 50% 资源使用
    MEDIUM = "medium"     # 50-75% 资源使用
    HIGH = "high"         # 75-85% 资源使用
    CRITICAL = "critical" # > 85% 资源使用


@dataclass
class ResourceState:
    """系统资源状态"""
    vram_total_gb: float = 103.0
    vram_used_gb: float = 0.0
    vram_free_gb: float = 103.0
    vram_percent: float = 0.0
    gpu_percent: float = 0.0
    cpu_percent: float = 0.0
    ram_total_gb: float = 32.0
    ram_available_gb: float = 21.0
    ram_percent: float = 0.0
    npu_available: bool = False
    npu_columns: int = 8
    # 功率监测
    gpu_power_w: float = 0.0       # GPU 当前功率 (W)
    gpu_power_cap_w: float = 0.0   # GPU 功率上限 (W)
    cpu_power_w: float = 0.0       # CPU 当前功率 (W)
    package_power_w: float = 0.0   # 整机功率 (W)
    gpu_temp_c: float = 0.0        # GPU 温度 (°C)
    cpu_temp_c: float = 0.0        # CPU 温度 (°C)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "vram_total_gb": round(self.vram_total_gb, 1),
            "vram_used_gb": round(self.vram_used_gb, 1),
            "vram_free_gb": round(self.vram_free_gb, 1),
            "vram_percent": round(self.vram_percent, 3),
            "gpu_percent": round(self.gpu_percent, 1),
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_total_gb": round(self.ram_total_gb, 1),
            "ram_available_gb": round(self.ram_available_gb, 1),
            "ram_percent": round(self.ram_percent, 1),
            "npu_available": self.npu_available,
            "npu_columns": self.npu_columns,
            # 功率和温度
            "gpu_power_w": round(self.gpu_power_w, 1),
            "gpu_power_cap_w": round(self.gpu_power_cap_w, 1),
            "cpu_power_w": round(self.cpu_power_w, 1),
            "package_power_w": round(self.package_power_w, 1),
            "gpu_temp_c": round(self.gpu_temp_c, 1),
            "cpu_temp_c": round(self.cpu_temp_c, 1),
            "timestamp": self.timestamp,
        }


class ResourceMonitor:
    """资源监控器 - 单例模式"""

    _instance: Optional["ResourceMonitor"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._history: List[ResourceState] = []
        self._max_history = 1000
        self._callbacks: List[Callable[[ResourceState], None]] = []
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

        # 尝试导入 psutil
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            self._psutil = None
            logger.warning("psutil 未安装，CPU/RAM 监控将使用默认值")

    def _detect_npu(self) -> bool:
        """检测 NPU 是否可用 (多种检测方式)"""
        # 方法 1: /dev/accel0 设备节点
        if os.path.exists("/dev/accel0"):
            return True

        # 方法 2: /sys/class/accel/accel0 (sysfs)
        if os.path.isdir("/sys/class/accel/accel0"):
            return True

        # 方法 3: lspci 检测 AMD NPU
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True, text=True, timeout=5
            )
            if "17f0" in result.stdout or "Neural Processing Unit" in result.stdout:
                return True
        except Exception:
            pass

        # 方法 4: 检查 amdxdna 内核模块
        try:
            result = subprocess.run(
                ["lsmod"],
                capture_output=True, text=True, timeout=5
            )
            if "amdxdna" in result.stdout:
                return True
        except Exception:
            pass

        return False

    def get_current_state(self) -> ResourceState:
        """获取当前系统资源状态"""
        state = ResourceState()

        # 获取 VRAM 信息
        try:
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'VRAM Total Memory' in line and 'Used' not in line:
                    # 格式: GPU[0]		: VRAM Total Memory (B): 103079215104
                    parts = line.split(':')
                    if len(parts) > 1:
                        value = parts[-1].strip().split()[0]
                        if value.isdigit():
                            state.vram_total_gb = int(value) / (1024**3)
                if 'VRAM Total Used Memory' in line:
                    # 格式: GPU[0]		: VRAM Total Used Memory (B): 41218314240
                    parts = line.split(':')
                    if len(parts) > 1:
                        value = parts[-1].strip().split()[0]
                        if value.isdigit():
                            state.vram_used_gb = int(value) / (1024**3)
        except Exception as e:
            logger.debug("获取 VRAM 信息失败: {}", e)

        state.vram_free_gb = state.vram_total_gb - state.vram_used_gb
        state.vram_percent = state.vram_used_gb / state.vram_total_gb if state.vram_total_gb > 0 else 0

        # 获取 GPU 使用率
        try:
            result = subprocess.run(
                ["rocm-smi", "--showuse"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                if 'GPU use' in line and '%' in line:
                    # 格式: GPU[0]		: GPU use (%): 100
                    parts = line.split(':')
                    if len(parts) > 1:
                        value_part = parts[-1].strip().replace('%', '').strip()
                        try:
                            state.gpu_percent = float(value_part)
                        except ValueError:
                            pass
                    break
        except Exception as e:
            logger.debug("获取 GPU 使用率失败: {}", e)

        # 获取 CPU 和 RAM
        if self._psutil:
            try:
                state.cpu_percent = self._psutil.cpu_percent(interval=0.1)
                ram = self._psutil.virtual_memory()
                state.ram_total_gb = ram.total / (1024**3)
                state.ram_available_gb = ram.available / (1024**3)
                state.ram_percent = ram.percent
            except Exception as e:
                logger.debug("获取 CPU/RAM 信息失败: {}", e)

        # 检查 NPU (多种检测方式)
        state.npu_available = self._detect_npu()

        # 获取 GPU 功率和温度
        try:
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--showtemp"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                # 温度信息 - 格式: GPU[0] : Temperature (Sensor edge) (C): 35.0
                if 'Temperature (Sensor edge)' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        value = parts[-1].strip().replace('C)', '').strip()
                        try:
                            state.gpu_temp_c = float(value)
                        except ValueError:
                            pass
                # 功率信息 - 格式: GPU[0] : Current Socket Graphics Package Power (W): 17.007
                if 'Package Power' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        value = parts[-1].strip().replace('W', '').strip()
                        try:
                            state.gpu_power_w = float(value)
                        except ValueError:
                            pass
        except Exception as e:
            logger.debug("获取 GPU 功率/温度失败: {}", e)

        # 获取 CPU 功率和温度
        if self._psutil:
            try:
                # CPU 温度
                if hasattr(self._psutil, 'sensors_temperatures'):
                    temps = self._psutil.sensors_temperatures()
                    if 'coretemp' in temps:
                        state.cpu_temp_c = temps['coretemp'][0].current
                    elif 'k10temp' in temps:
                        state.cpu_temp_c = temps['k10temp'][0].current

                # CPU 功率 (通过 RAPL 或估算)
                if hasattr(self._psutil, 'sensors_battery'):
                    battery = self._psutil.sensors_battery()
                    if battery:
                        state.package_power_w = battery.power_plugged and 0 or 0

                # 尝试从 /sys 读取 AMD RAPL 功率
                try:
                    with open('/sys/class/hwmon/hwmon2/power1_average', 'r') as f:
                        state.cpu_power_w = int(f.read().strip()) / 1000000  # 微瓦转瓦
                except:
                    pass
            except Exception as e:
                logger.debug("获取 CPU 功率/温度失败: {}", e)

        # 更新时间戳
        state.timestamp = time.time()

        return state

    def get_load_level(self, state: Optional[ResourceState] = None) -> LoadLevel:
        """获取系统负载级别"""
        if state is None:
            state = self.get_current_state()

        if state.vram_percent >= 0.95:
            return LoadLevel.CRITICAL
        elif state.vram_percent >= 0.85:
            return LoadLevel.HIGH
        elif state.vram_percent >= 0.50:
            return LoadLevel.MEDIUM
        else:
            return LoadLevel.LOW

    def add_to_history(self, state: ResourceState):
        """添加到历史记录"""
        self._history.append(state)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, limit: int = 100) -> List[ResourceState]:
        """获取历史记录"""
        return self._history[-limit:]

    def add_callback(self, callback: Callable[[ResourceState], None]):
        """添加状态变化回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[ResourceState], None]):
        """移除回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start_monitoring(self, interval: float = 5.0):
        """启动后台监控"""
        if self._monitoring:
            return

        self._monitoring = True

        def _monitor_loop():
            while self._monitoring:
                try:
                    state = self.get_current_state()
                    self.add_to_history(state)

                    # 获取负载级别
                    load_level = self.get_load_level(state)

                    # 保存指标到数据库（每分钟保存一次，避免频繁写入）
                    if int(time.time()) % 60 < interval:
                        self.save_metric_to_db(state, load_level)

                    # 检查并保存预警
                    self.check_and_save_alerts(state)

                    # 触发回调
                    for callback in self._callbacks:
                        try:
                            callback(state)
                        except Exception as e:
                            logger.error("资源监控回调错误: {}", e)

                    time.sleep(interval)
                except Exception as e:
                    logger.error("资源监控循环错误: {}", e)
                    time.sleep(interval)

        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("资源监控已启动 (间隔: {}s)", interval)

    def stop_monitoring(self):
        """停止后台监控"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        logger.info("资源监控已停止")

    def get_summary(self) -> dict:
        """获取资源摘要"""
        state = self.get_current_state()
        load_level = self.get_load_level(state)

        return {
            "state": state.to_dict(),
            "load_level": load_level.value,
            "history_count": len(self._history),
        }

    def check_and_save_alerts(self, state: ResourceState) -> List[dict]:
        """检查资源状态并保存预警到数据库"""
        alerts = []
        load_level = self.get_load_level(state)

        # VRAM 高使用率预警
        if state.vram_percent >= 0.95:
            alerts.append({
                "alert_type": "vram_high",
                "severity": "critical",
                "title": "VRAM 使用率极高",
                "message": f"VRAM 使用率已达 {state.vram_percent:.1%}，可能导致服务不可用",
                "vram_percent": state.vram_percent,
            })
        elif state.vram_percent >= 0.85:
            alerts.append({
                "alert_type": "vram_high",
                "severity": "warning",
                "title": "VRAM 使用率偏高",
                "message": f"VRAM 使用率为 {state.vram_percent:.1%}，建议优化资源配置",
                "vram_percent": state.vram_percent,
            })

        # GPU 高使用率预警
        if state.gpu_percent >= 95:
            alerts.append({
                "alert_type": "gpu_high",
                "severity": "critical",
                "title": "GPU 使用率极高",
                "message": f"GPU 使用率已达 {state.gpu_percent:.1f}%，可能影响服务质量",
                "gpu_percent": state.gpu_percent,
            })

        # CPU 高使用率预警
        if state.cpu_percent >= 90:
            alerts.append({
                "alert_type": "cpu_high",
                "severity": "warning",
                "title": "CPU 使用率偏高",
                "message": f"CPU 使用率为 {state.cpu_percent:.1f}%",
                "cpu_percent": state.cpu_percent,
            })

        # GPU 温度预警
        if state.gpu_temp_c >= 90:
            alerts.append({
                "alert_type": "temp_high",
                "severity": "critical",
                "title": "GPU 温度过高",
                "message": f"GPU 温度已达 {state.gpu_temp_c:.0f}°C，存在降频风险",
                "gpu_temp_c": state.gpu_temp_c,
            })
        elif state.gpu_temp_c >= 80:
            alerts.append({
                "alert_type": "temp_high",
                "severity": "warning",
                "title": "GPU 温度偏高",
                "message": f"GPU 温度为 {state.gpu_temp_c:.0f}°C",
                "gpu_temp_c": state.gpu_temp_c,
            })

        # GPU 功率预警
        if state.gpu_power_w > 0 and state.gpu_power_cap_w > 0:
            power_ratio = state.gpu_power_w / state.gpu_power_cap_w
            if power_ratio >= 0.95:
                alerts.append({
                    "alert_type": "power_high",
                    "severity": "warning",
                    "title": "GPU 功率接近上限",
                    "message": f"GPU 功率 {state.gpu_power_w:.0f}W / {state.gpu_power_cap_w:.0f}W ({power_ratio:.0%})",
                    "gpu_power_w": state.gpu_power_w,
                })

        # NPU 离线预警
        if not state.npu_available:
            alerts.append({
                "alert_type": "npu_offline",
                "severity": "info",
                "title": "NPU 设备不可用",
                "message": "NPU 设备未检测到，ASR 将使用 CPU 模式",
            })

        # 保存到数据库
        if alerts:
            self._save_alerts_to_db(alerts, state, load_level)

        return alerts

    def save_metric_to_db(self, state: ResourceState, load_level: LoadLevel):
        """保存资源指标到数据库"""
        try:
            from ..database import SessionLocal
            from ..models.models import ResourceMetric
            from ..core.resource_rules import resource_rule_engine

            db = SessionLocal()
            try:
                metric = ResourceMetric(
                    vram_percent=state.vram_percent,
                    gpu_percent=state.gpu_percent,
                    cpu_percent=state.cpu_percent,
                    ram_percent=state.ram_percent,
                    gpu_power_w=state.gpu_power_w,
                    gpu_power_cap_w=state.gpu_power_cap_w,
                    cpu_power_w=state.cpu_power_w,
                    package_power_w=state.package_power_w,
                    gpu_temp_c=state.gpu_temp_c,
                    cpu_temp_c=state.cpu_temp_c,
                    load_level=load_level.value,
                    policy_name=resource_rule_engine.current_policy.value,
                )
                db.add(metric)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.debug("保存资源指标失败: {}", e)

    def _save_alerts_to_db(self, alerts: List[dict], state: ResourceState, load_level: LoadLevel):
        """保存预警到数据库"""
        try:
            from ..database import SessionLocal
            from ..models.models import ResourceAlert
            from ..core.resource_rules import resource_rule_engine

            db = SessionLocal()
            try:
                for alert_data in alerts:
                    # 检查是否已有相同类型的活跃预警（避免重复）
                    existing = db.query(ResourceAlert).filter(
                        ResourceAlert.alert_type == alert_data["alert_type"],
                        ResourceAlert.status == "active",
                    ).first()

                    if not existing:
                        alert = ResourceAlert(
                            alert_type=alert_data["alert_type"],
                            severity=alert_data["severity"],
                            title=alert_data["title"],
                            message=alert_data["message"],
                            vram_percent=alert_data.get("vram_percent"),
                            gpu_percent=alert_data.get("gpu_percent"),
                            cpu_percent=alert_data.get("cpu_percent"),
                            gpu_power_w=alert_data.get("gpu_power_w"),
                            gpu_temp_c=alert_data.get("gpu_temp_c"),
                            cpu_temp_c=alert_data.get("cpu_temp_c"),
                            policy_name=resource_rule_engine.current_policy.value,
                        )
                        db.add(alert)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.debug("保存资源预警失败: {}", e)


# 全局单例
resource_monitor = ResourceMonitor()
