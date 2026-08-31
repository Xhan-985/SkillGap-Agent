# UI_SPEC —— 前端页面规格（Phase 1）

> SkillGap Agent ｜ Phase 1 交付物
> 设计原则：**展示数据、证据和决策，不是聊天框。** 每个数字可点击溯源；样本不足时明示；数据窗口与来源分布常驻可见。MVP 不做花哨 UI——简洁单页应用（服务端渲染或轻前端均可，Phase 10 实现）。

---

## 1. 信息架构

```
SkillGap Agent
├── Dashboard（首页，六视图总览）
├── JD Analysis（粘贴 JD → 结构化分析 → 贡献入口）
├── Resume Analysis（画像 + 证据链）
├── Job Matching（匹配 breakdown + 三组技能）
├── Recommendation（ROI 表 + Priority + 项目建议）
├── Market（频率统计，China/Global 切换）
└── Data & Quality（数据透明度页：来源/样本量/质量指标）
```

全局常驻：市场选择器（China 🇨🇳 / Global 🌍，不可同时）｜ 数据窗口标注 ｜ "Jobs by Adzuna" 归属标识（仅 Global 数据视图）。

---

## 2. 页面规格

### 2.1 Dashboard（M10 六视图）

| 视图 | 内容 | 交互 |
|---|---|---|
| 我的画像 | 技能星级 + confidence 色阶（高置信深色/低置信浅色+问号） | 点击技能 → 证据链弹层 |
| 技能雷达 | 画像 vs 目标岗位要求叠加雷达图 | 切换目标岗位 |
| 市场热门技能 | 频率条形图，**每条附 N 与置信度标签**（如 "Python 80% · N=240 · medium"） | 点击条 → 溯源 JD 列表 |
| 我的缺口 | ROI 排序表（Skill/Demand/Gap/Cost/Potential Gain） | 点击 → 详情 |
| 推荐行动 | Priority 1/2/3 卡片 + 理由摘要 | → Recommendation 页 |
| 匹配概览 | 最近匹配分数 breakdown 四条形 | → Matching 页 |

**样本量守门在 UI 呈现**：任何统计卡片在 N<30 时渲染为灰色占位 + "样本量不足以判断趋势（N=xx）"，不隐藏、不降级为无标注数字。

### 2.2 JD Analysis（M1 + M3）

1. **输入区**：大文本框（50-20000 字符计数器）+ 粘贴板快捷按钮
2. **结果区**（结构化呈现，非流水文本）：
   - 岗位卡：标题/类别/城市/市场/薪资
   - 核心技能（must_have）与次要技能（nice_to_have）分栏；每技能 chip 附证据片段（灰底引用块，点击高亮原文位置）
   - 软性要求列表
   - 抽取元信息折叠条（模型/prompt_version/延迟——透明度）
3. **贡献区**（分析完成后出现）：
   - 复选框（默认未勾）："匿名贡献到市场数据集"
   - 提交后：PII 命中摘要（"检测并替换了 1 处联系方式"）+ **deletion_code 一次性展示弹窗**（强提示保存）+ 来源提示单选（boss/nowcoder/other，仅统计标签）
4. **失败态**：抽取失败红色横幅 + 重试按钮（不静默降级）；quarantine 结果给出原因与人工复核说明

### 2.3 Resume Analysis（M5）

1. 输入：文本粘贴（Should Have：PDF 上传）
2. 画像页：
   - 技能卡列表：星级 + confidence 数值 + **证据链折叠区**（每条证据带类型标签与权重，如 "项目细节 ×1.0"）
   - "声明 vs 证明"对照视觉：bare_claim 类证据用虚线边框警示样式（对应"了解 MCP → 0.45"）
   - confidence 计算规则说明入口（公式公开链接）
3. 删除入口：清空画像（二次确认，说明级联删除范围）

### 2.4 Job Matching（M6）

1. 入口：选择已分析 JD（或粘贴新 JD）+ 当前画像
2. 结果页：
   - **总分与四项 breakdown 并排**（总分大数字 + 四条形：coverage/importance/evidence/experience）——总分从不单独出现
   - Strong/Weak/Missing 三列泳道：每技能附 JD 侧证据（缺什么）与简历侧证据（有什么），行内可跳转
   - 解释文本区（LLM 生成，数字由 breakdown 渲染插入；附"数值与解释一致性已程序校验"标识）
   - scoring_version 显示（右下角小字）

### 2.5 Recommendation（M9）

1. 输入：时间预算选择（7/14/30 天）+ 目标市场
2. ROI 表：Skill ｜ Demand（附 N）｜ Gap ｜ Cost ｜ Potential Gain——**五列齐全，Gain 可点击展开公式代入过程**
3. Priority 1/2/3 卡片：技能 + 三段式理由（需求证据/当前缺口/成本收益）
4. 项目建议区（Should Have）：模板卡片（技能覆盖 + 预估天数 + "模板人工策划"标注）
5. 免责线：Demand 引用快照口径（点击回 Market 页对应窗口）

### 2.6 Market（M8）

1. 市场切换 Tab：China / Global（**单一市场视图，无合并视图**）
2. 过滤器：岗位类别/城市/时间窗
3. 统计主体：技能频率表（技能/频率/jd_count/置信度徽章/来源分布 tooltip）
4. 每行"查看证据"→ 溯源列表页：JD 标题 + source_type 徽章 + source_url 外链（public_job_page 时）+ 证据片段
5. 顶部口径说明条："本统计基于 N 条 JD，窗口 2026-08-01~08-31，来源：用户贡献 55% / 公开页面 32% / 导入 13%"
6. Global 视图右下角常驻："Jobs by Adzuna"（链接 adzuna.co.uk）

### 2.7 Data & Quality（透明度页）

- 来源分布图（Tier A/B/C + source_name 明细）
- E5 数据质量五指标卡（duplicate/missing/PII/invalid/extraction error rate）
- 治理声明摘要 + 链接到 DATA_GOVERNANCE（反爬声明/PII 边界/保留策略）
- 各外部源条款核查日期（terms_checked_at）

---

## 3. 交互纪律（全站）

1. **无聊天框为主交互**：开放问答（RAG）是 Phase 8+ 附加能力，不是主界面
2. **数字必带口径**：任何百分比/分数出现处，N 与窗口可即时查看（tooltip 或角标）
3. **证据即导航**：evidence_ref 是一等公民，点击必达
4. **诚实降级样式**：样本不足/抽取失败/quarantine 各有专属视觉态，禁止空白或假装成功
5. 移动端不优化（MVP 桌面优先）；无框架级动画投入
