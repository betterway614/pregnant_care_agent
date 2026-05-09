"""
知识库文档向量化入库脚本
用法: python scripts/ingest_knowledge.py [--force]

流程:
1. 读取 knowledge_docs/ 下所有 .md 文件
2. 按 ## 章节分割成chunk
3. 调用embedding服务生成向量
4. 存入PostgreSQL pgvector
"""
import os, sys, re, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal, engine
from app.models.vector_models import KnowledgeChunk
from app.core.embedding import get_embedding_client


def parse_markdown(filepath: str) -> list[dict]:
    """解析Markdown文件，按##章节分割"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 提取文档标题（第一个 # ）
    title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
    doc_title = title_match.group(1).strip() if title_match else os.path.basename(filepath)

    # 确定分类
    category_map = {
        "guideline": ["孕期保健", "指南", "prenatal"],
        "drug": ["用药", "药物", "medication"],
        "education": ["教育", "心理", "母乳", "产后", "新生儿", "护理", "皮肤", "口腔", "旅行", "health_edu"],
    }
    doc_category = "general"
    fname = os.path.basename(filepath).lower()
    for cat, keywords in category_map.items():
        if any(k in fname for k in keywords):
            doc_category = cat
            break

    # 按 ## 分割章节
    sections = re.split(r"\n(?=##\s)", content)
    chunks = []
    for i, section in enumerate(sections):
        # 跳过没有实质内容的section
        stripped = section.strip()
        if len(stripped) < 50:
            continue
        # 提取章节标题
        sec_title = re.search(r"^##\s+(.+)", section, re.MULTILINE)
        section_name = sec_title.group(1).strip() if sec_title else f"第{i+1}章"

        chunks.append({
            "doc_title": f"{doc_title} - {section_name}",
            "doc_category": doc_category,
            "chunk_index": i,
            "content": stripped,
        })
    return chunks


def ingest(force: bool = False):
    """主入库流程"""
    from app.database import SessionLocal
    db = SessionLocal()

    # 检查是否已入库
    existing = db.query(KnowledgeChunk).count()
    if existing > 0 and not force:
        print(f"知识库已有 {existing} 条记录，跳过入库（使用 --force 强制重新入库）")
        db.close()
        return

    if force:
        print("清空已有知识库...")
        db.query(KnowledgeChunk).delete()
        db.commit()

    # 扫描文档
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_docs")
    if not os.path.isdir(docs_dir):
        print(f"知识库目录不存在: {docs_dir}")
        db.close()
        return

    md_files = [f for f in os.listdir(docs_dir) if f.endswith(".md")]
    if not md_files:
        print("未找到Markdown文件，使用内置知识...")
        all_chunks = _builtin_knowledge()
    else:
        print(f"找到 {len(md_files)} 个文档文件")
        all_chunks = []
        for fname in md_files:
            fpath = os.path.join(docs_dir, fname)
            chunks = parse_markdown(fpath)
            all_chunks.extend(chunks)
            print(f"  {fname}: {len(chunks)} 个章节")

    if not all_chunks:
        print("未提取到任何内容")
        db.close()
        return

    print(f"共 {len(all_chunks)} 个文本块")

    # 生成向量
    embedding = get_embedding_client()
    texts = [c["content"] for c in all_chunks]
    print(f"正在为 {len(texts)} 个文本块生成向量...")
    try:
        vectors = embedding.embed(texts)
    except Exception as e:
        print(f"Embedding失败: {e}，使用零向量")
        vectors = [[0.0] * 1024 for _ in texts]

    # 存入数据库（pgvector）
    from app.config import settings
    if settings.db_type != "postgres":
        print("当前使用SQLite，向量检索将降级为关键词匹配")
        _save_to_db(db, all_chunks, vectors)
    else:
        _save_with_pgvector(db, all_chunks, vectors)

    db.close()
    print("入库完成")


def _save_to_db(db, chunks, vectors):
    """普通SQLite存储"""
    import uuid
    for chunk, vec in zip(chunks, vectors):
        kc = KnowledgeChunk(
            id=uuid.uuid4(),
            doc_title=chunk["doc_title"],
            doc_category=chunk["doc_category"],
            chunk_index=chunk["chunk_index"],
            content=chunk["content"],
            metadata={"embedding_dim": len(vec)},
        )
        db.add(kc)
    db.commit()
    print(f"已存入 {len(chunks)} 条记录（SQLite模式）")


def _save_with_pgvector(db, chunks, vectors):
    """pgvector原生向量存储"""
    for chunk, vec in zip(chunks, vectors):
        vec_str = "[" + ",".join(str(v) for v in vec) + "]"
        from sqlalchemy import text
        db.execute(
            text("""
                INSERT INTO knowledge_chunks (id, doc_title, doc_category, chunk_index, content, embedding, metadata)
                VALUES (gen_random_uuid(), :title, :cat, :idx, :content, :vec::vector, :meta)
            """),
            {
                "title": chunk["doc_title"],
                "cat": chunk["doc_category"],
                "idx": chunk["chunk_index"],
                "content": chunk["content"],
                "vec": vec_str,
                "meta": '{"source": "ingest_script"}',
            }
        )
    db.commit()
    print(f"已存入 {len(chunks)} 条记录（pgvector模式）")


def _builtin_knowledge() -> list[dict]:
    """内置知识库（知识文档不存在时的兜底）"""
    return [
        {
            "doc_title": "孕期营养指导",
            "doc_category": "guideline",
            "chunk_index": 0,
            "content": (
                "## 孕期营养指导\n\n"
                "孕期营养对母婴健康至关重要。孕早期（1-12周）需补充叶酸0.4mg/天预防神经管畸形。"
                "孕中期（13-28周）增加钙（1000mg/天）、铁（30mg/天）、DHA（200mg/天）摄入。"
                "孕晚期（29-40周）继续高蛋白饮食。推荐食物：深绿色蔬菜、红肉、鱼类（避免高汞鱼）、"
                "鸡蛋、牛奶。避免：生食、酒精、过量咖啡因（<200mg/天）。"
            ),
        },
        {
            "doc_title": "胎动自我监测指南",
            "doc_category": "guideline",
            "chunk_index": 1,
            "content": (
                "## 胎动自我监测指南\n\n"
                "从孕28周开始，建议孕妇每日固定时间（建议饭后1小时）计数胎动。"
                "正常胎动：每小时3-5次，12小时累计≥30次。异常信号：12小时胎动<10次，"
                "或胎动突然减少50%以上，需立即就医。胎动消失是最危险的信号，"
                "一旦发现应立即前往医院急诊。"
            ),
        },
        {
            "doc_title": "临产征兆与分娩准备",
            "doc_category": "guideline",
            "chunk_index": 2,
            "content": (
                "## 临产征兆与分娩准备\n\n"
                "真宫缩特征：规律性（每隔5-10分钟一次）、逐渐增强、伴有宫颈扩张。"
                "假宫缩(Braxton Hicks)：不规则、间歇性、休息可缓解。见红：阴道少量血性分泌物，"
                "通常24-48小时内启动分娩。破水：阴道突然流出液体，需立即就医（脐带脱垂风险）。"
                "待产包：身份证、医保卡、产检档案、产妇垫、换洗衣物、新生儿用品。"
            ),
        },
        {
            "doc_title": "孕期用药安全原则",
            "doc_category": "drug",
            "chunk_index": 3,
            "content": (
                "## 孕期用药安全原则\n\n"
                "FDA妊娠用药分级：A级（安全，如叶酸）、B级（相对安全，如青霉素类、对乙酰氨基酚）、"
                "C级（需评估风险收益）、D级（有证据的风险，仅在危及生命时使用）、"
                "X级（绝对禁用，如异维A酸）。孕期退烧首选对乙酰氨基酚，避免布洛芬和阿司匹林等NSAIDs。"
                "抗生素首选青霉素类和头孢菌素类，禁用四环素类（影响胎儿骨骼牙齿发育）。"
                "所有用药须在医生指导下进行。"
            ),
        },
        {
            "doc_title": "妊娠期高血压管理",
            "doc_category": "drug",
            "chunk_index": 4,
            "content": (
                "## 妊娠期高血压管理\n\n"
                "诊断标准：收缩压≥140mmHg或舒张压≥90mmHg（两次测量间隔4小时以上）。"
                "一线降压药：拉贝洛尔（α+β受体阻滞剂）为首选，硝苯地平（钙通道阻滞剂）为备选。"
                "绝对禁用：ACEI类（如卡托普利）和ARB类（如缬沙坦）——可导致胎儿肾发育异常。"
                "目标血压：控制在130-155/80-105mmHg。需同时监测尿蛋白（排除子痫前期）、"
                "血小板和肝功能。"
            ),
        },
        {
            "doc_title": "孕期心理健康",
            "doc_category": "education",
            "chunk_index": 5,
            "content": (
                "## 孕期心理健康\n\n"
                "孕期情绪波动是正常现象，约15-20%孕妇会出现焦虑或抑郁症状。"
                "CBT小技巧：1）识别自动负性思维，2）用积极替代，3）行为激活（规律作息运动）。"
                "正念呼吸：深吸气4秒→屏息4秒→慢呼气4秒，每天练习3-5分钟。"
                "如情绪低落持续超2周、影响日常生活、出现自杀念头，需立即求助心理科。"
                "心理援助热线：400-161-9995。家人陪伴和理解是预防产后抑郁的关键。"
            ),
        },
        {
            "doc_title": "孕期体重管理",
            "doc_category": "guideline",
            "chunk_index": 6,
            "content": (
                "## 孕期体重管理\n\n"
                "BMI正常孕妇（18.5-24.9）：孕期增重11.5-16kg，每周0.4-0.5kg。"
                "孕早期增重1-2kg，孕中晚期每周增重0.4kg左右。体重增长过快（>2kg/周）"
                "提示水肿、妊娠期糖尿病或营养过剩风险。体重增长过慢需评估胎儿生长。"
                "每周固定时间、同一台秤测量体重并记录。"
            ),
        },
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知识库向量化入库")
    parser.add_argument("--force", action="store_true", help="强制重新入库")
    args = parser.parse_args()

    ingest(force=args.force)
