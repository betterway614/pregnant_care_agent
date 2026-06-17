"""患者-超声图像映射（脱敏：按索引分配，不暴露真实姓名）"""
import os
import json

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_NOR_DIR = os.path.join(MODULE_DIR, "photo", "raw", "nor")
RAW_FGR_DIR = os.path.join(MODULE_DIR, "photo", "raw", "fgr")
MASK_NOR_DIR = os.path.join(MODULE_DIR, "photo", "mask", "nor")
MASK_FGR_DIR = os.path.join(MODULE_DIR, "photo", "mask", "fgr")

UPLOAD_DIR = os.path.join(MODULE_DIR, "uploads")
PATIENT_IMAGE_MAP_PATH = os.path.join(MODULE_DIR, "patient_image_map.json")


def _scan_pairs(raw_dir: str, mask_dir: str) -> list[tuple[str, str]]:
    """扫描目录，返回排序后的 (raw_path, mask_path) 配对列表"""
    if not os.path.isdir(raw_dir) or not os.path.isdir(mask_dir):
        return []

    mask_map = {}
    for f in os.listdir(mask_dir):
        if f.endswith(".png"):
            mask_map[f.replace(".png", "")] = os.path.join(mask_dir, f)

    pairs = []
    for f in sorted(os.listdir(raw_dir)):
        if not f.endswith(".png"):
            continue
        key = f.replace("_0000.png", "").replace(".png", "")
        if key in mask_map:
            pairs.append((os.path.join(raw_dir, f), mask_map[key]))
    return pairs


def get_image_pairs() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """返回 (nor_pairs, fgr_pairs)，按文件名排序"""
    nor_pairs = _scan_pairs(RAW_NOR_DIR, MASK_NOR_DIR)
    fgr_pairs = _scan_pairs(RAW_FGR_DIR, MASK_FGR_DIR)
    return nor_pairs, fgr_pairs


def load_patient_map() -> dict[str, dict]:
    """加载患者-图片映射文件"""
    if not os.path.exists(PATIENT_IMAGE_MAP_PATH):
        return {}
    with open(PATIENT_IMAGE_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_patient_map(mapping: dict[str, dict]) -> None:
    """保存患者-图片映射文件"""
    os.makedirs(os.path.dirname(PATIENT_IMAGE_MAP_PATH), exist_ok=True)
    with open(PATIENT_IMAGE_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def get_patient_images(pregnant_id: str) -> tuple[str, str] | None:
    """根据 pregnant_id 查找患者绑定的 (raw_path, mask_path)"""
    mapping = load_patient_map()
    entry = mapping.get(pregnant_id)
    if entry:
        return entry["raw_path"], entry["mask_path"]
    return None


def get_patient_group(pregnant_id: str) -> str | None:
    """获取患者的真实分组标签（NOR/FGR/upload），用于精度验证"""
    mapping = load_patient_map()
    entry = mapping.get(pregnant_id)
    if entry:
        return entry.get("group")
    return None


def remap_patient_ids(db_session) -> int:
    """自动修复 patient_image_map.json 中的 ID 漂移（DB 重置后 ID 变化但 display_name 不变）。

    通过 display_name 匹配 DB 记录与映射条目，将旧 ID 替换为当前 DB ID。

    Args:
        db_session: SQLAlchemy Session 实例

    Returns:
        重映射的条目数
    """
    mapping = load_patient_map()
    if not mapping:
        return 0

    # 导入 Pregnant 模型
    from app.models import Pregnant
    patients = db_session.query(Pregnant.pregnant_id, Pregnant.display_name).all()
    db_name_to_id: dict[str, str] = {name: pid for pid, name in patients}

    new_map: dict[str, dict] = {}
    remapped = 0
    for old_id, entry in mapping.items():
        # 如果旧 ID 已在 DB 中，保持不变
        if old_id in {p.pregnant_id for p in patients}:
            new_map[old_id] = entry
            continue

        # 尝试通过 display_name 匹配
        name = entry.get("display_name", "")
        db_id = db_name_to_id.get(name)
        if db_id:
            new_map[db_id] = entry
            remapped += 1
        else:
            # 无法匹配，保留旧条目
            new_map[old_id] = entry

    if remapped > 0:
        save_patient_map(new_map)

    return remapped


def register_uploaded_images(pregnant_id: str, display_name: str,
                             image_bytes: bytes, mask_bytes: bytes) -> tuple[str, str]:
    """上传超声图像并注册到映射表，返回 (raw_path, mask_path)"""
    patient_dir = os.path.join(UPLOAD_DIR, pregnant_id)
    os.makedirs(patient_dir, exist_ok=True)

    raw_path = os.path.join(patient_dir, "image.png")
    mask_path = os.path.join(patient_dir, "mask.png")

    with open(raw_path, "wb") as f:
        f.write(image_bytes)
    with open(mask_path, "wb") as f:
        f.write(mask_bytes)

    # 更新映射表
    mapping = load_patient_map()
    mapping[pregnant_id] = {
        "display_name": display_name,
        "raw_path": raw_path,
        "mask_path": mask_path,
        "group": "upload",
    }
    save_patient_map(mapping)

    return raw_path, mask_path
