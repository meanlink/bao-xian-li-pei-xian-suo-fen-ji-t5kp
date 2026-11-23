# 保险理赔线索分级

面向华东安心保险理赔中心的小型理赔线索分级工作台。它把报案受理、缺项补件、资料核验、风险分级和调查派单串在同一条理赔作业链上。

## 启动

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python scripts/seed_demo.py
```

访问 `http://localhost:18244`。演示账号统一密码为 `demo123`。

| 账号 | 角色 | 主要动作 |
|---|---|---|
| intake@claims.local | 案件受理员 | 新建案件、登记补件联系、核验资料 |
| investigator@claims.local | 调查员 | 查看线索、完成调查、提交和补正核验证据 |
| manager@claims.local | 风险主管 | 跟进逾期补件、模型分级、阈值评估回滚、主管复核、核赔结案 |

## 业务链

报案 → 初审 → 模型分级 → 调查 → 核赔。资料不完整的案件不能进入模型。阈值评估若误报率超过 25%，系统恢复上一个可用阈值并记录审计日志。

## 补件调度

受理员登录后打开「补件调度」。演示案件 `CLM-261102-0002` 缺少损失清单，尚未登记补件联系。登记沟通渠道、联系日期、约定补件期限与沟通结果。调度队列使用北京时间，把逾期、今日到期、待首次联系和等待补件的案件依次排开。同一组先处理期限更早的案件，期限相同则先处理损失金额较高的案件。

从队列进入「资料核验」勾选每件已经收到的材料。只收到一部分时，剩余缺项仍留在原期限，风险分级继续被阻断。全部核齐时，资料核验与补件回执在同一事务保存，案件退出补件队列并可由主管分级。在分级前纠正误勾的资料会重新进入队列，之前的回执保留。已经分级或进入后续流程的案件禁止将资料改回缺项。

补件联系记录仅向受理员和风险主管开放。重复登记、过时的联系版本和过时的缺项清单会收到冲突提示。该工作台登记已发生的联系，实际电话、短信与邮件由经办人在线下完成。

## 线索证据复核

试用案件 `CLM-261105-0005` 的「出险时间异常」线索。调查员在「证据复核」填写凭证类型、可追溯的编号、核验发现和证实或排除建议。风险主管可采纳建议并更新线索状态，也可注明缺项后退回补正。原调查员提交补正时进入下一轮，历史材料和每轮决定写入审计。受理员可查看进度。

仅调查中或待核赔案件的待核查线索可提交证据。已提交但待复核或待补正的记录会阻止核赔结案，案件详情显示对应数量和入口。主管决定会更新线索状态，历史模型分数保留原值。

后端启动时幂等创建复核表和补件跟进表，已有数据库卷可直接升级。重复运行演示 seed 会保留已经处理的理赔案件、线索和复核记录。

## 共享枚举

- 案件状态：`intake / initial_review / modeled / investigating / adjudicating / closed / rejected`
- 风险等级：`low / medium / high`
- 调查任务状态：`queued / assigned / in_progress / completed / cancelled`

案件、风险与调查任务枚举在 `backend/src/constants/enums.py` 和 `frontend/src/utils/constants.js`。线索状态、凭证来源和复核状态用于 `backend/migrations/001_schema.sql`、`backend/migrations/002_clue_reviews.sql`、`backend/src/schemas/clue_reviews.py` 和 `frontend/src/utils/constants.js`。

补件渠道 `phone / sms / email` 见 `backend/migrations/003_document_followups.sql`、`backend/src/schemas/claims.py` 与 `frontend/src/pages/documentTriage.js`。队列状态由 `backend/src/services/document_triage_service.py` 计算，前端负责展示与筛选。
