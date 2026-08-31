# ADR-004：为什么/为什么不使用 pgvector？

状态：**已接受（Phase 1 冻结：表结构预留、不建索引、不装依赖直到启用）** ｜ 日期：2026-08-31

## Context

RAG 是本项目 Phase 8+ 的候选能力（"为什么推荐我学 MCP"→ 检索 JD 数据/频率口径生成带引用回答）。pgvector 是 PostgreSQL 向量扩展，但 v1（M1-M11）的匹配与统计**全部基于结构化技能关系**（job_skill 表 + SQL），无任何向量检索需求。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **立即启用（建表+索引+依赖）** | 技术上"看起来完整" | v1 无使用场景 → 纯粹的过度设计（违反需求第一节"不为技术而技术"）；增加镜像体积与迁移负担 |
| **完全不用（不预留）** | 最简 | Phase 8 若启用 RAG 需表迁移；"预留 vs 迁移"成本不对称 |
| **表结构预留、不建索引** | 届时启用零迁移；当下零运行成本 | jd_embedding 空表（少量结构噪音） |

## Decision

**表结构预留（jd_embedding：job_id/model/dim/embedding），不建索引、不装扩展依赖；Phase 8 启用 RAG 时再 CREATE INDEX + 安装扩展。**

## Consequences

- 正面：Phase 8 决策自由（启用或放弃均无迁移）；v1 零依赖零成本
- 负面：若 Phase 8 最终不做 RAG，预留表是可接受的少量浪费（一张空表）

## Reversibility

撤销成本：**极低**（删表即可）。
复议触发条件：Phase 8 引入 RAG 问答（或归一层需嵌入相似度辅助排序——DATA_PIPELINE S9 的可选增强）时启用。
