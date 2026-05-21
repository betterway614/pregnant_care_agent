# Research Plan: 孕期随访记录归档格式规范

## Research question
孕期随访记录归档的最佳格式规范是什么？当前系统的 FollowUpRecord 模型如何优化以贴近行业标准？

## Intended audience
医疗AI产品团队（开发、产品），需要可直接落地的数据库模型和API设计建议。

## Freshness requirement
近5年（2022-2026），重点关注国内卫健委规范和SOAP笔记标准。

## Geography
中国大陆为主，参考国际标准（SOAP、FHIR）作为补充。

## Output type
**Brief memo**（1500-2500字），含可直接落地的字段设计建议。

## Stakes
Medium — 影响产品数据架构和后续互操作性。

## Why this skill is justified
- 需要跨多个来源（政策文件、医学标准、技术方案）的综合分析
- 决策涉及数据库schema设计，需要证据支撑
- 用户需要可复用的研究产物

## Research threads

### Thread A: 国内外孕期随访记录标准格式
- 国家基本公共卫生服务规范（第三版/第四版）中孕产妇健康管理记录表
- SOAP笔记格式在产科随访中的应用
- FHIR maternity care 相关资源

### Thread B: 随访归档核心字段设计
- 结构化 vs 非结构化数据比例
- 当前系统 FollowUpRecord 模型对比行业标准
- 数字化随访记录的最佳实践

### Thread C: AI生成报告与结构化记录的融合
- AI分析报告如何有机嵌入档案记录
- 审核流程设计
- 可追溯性与审计要求
