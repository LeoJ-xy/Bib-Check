# Bib-Check：BibTeX 引用真实性/一致性校验器

## 简介

Bib-Check 是面向科研/工程工作流的 BibTeX 校验与联网矫正工具。默认只检查，不修改文件；显式开启 fix/autofix 才会生成修复版 bib 与变更日志。核心能力：

- 静态检查：解析错误、重复 citekey、必填字段缺失、年份/DOI/URL 格式、pages 规范化等。
- 联网一致性：Crossref/OpenAlex/Semantic Scholar + arXiv/DBLP/CITATION.cff，标题/作者/年份/venue 对齐，DOI 找不到/不匹配报警，低置信匹配进入人工核对。
- Auto-fix（可选）：高置信补 DOI/作者/标题/年份/venue/pages；arXiv DOI 归一化；pages 规范化。
- Blog-aware（可选）：识别研究博客/项目页（OpenAI/Anthropic/Transformer Circuits 等），抓取网页元数据/官方 BibTeX，补全 title/author/date/url/howpublished/note。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 快速开始

- 仅检查（默认联网）：`python -m bibcheck sample.bib`
- 显式离线：`python -m bibcheck sample.bib --offline`
- 生成修复建议/文件（传统 fix，主要针对 DOI/元数据高置信修复）：`python -m bibcheck sample.bib --fix`
- 联网自动矫正（含 blog-aware，高置信>=0.85 自动写回，其余为建议）：`python -m bibcheck sample.bib --autofix --outdir out --min-conf 0.85 --autofix-scope high`
- 只想预览变更可加 `--dry-run`；`--no-network` 可禁用联网。

## 常用参数

- `--outdir out` 报告/输出目录
- `--max-entries N` 只检查前 N 条
- `--sources crossref,openalex,s2` 在线数据源（论文类检索）
- `--enable-arxiv` / `--disable-arxiv` 启用/禁用 arXiv API（默认开启）
- `--enable-dblp` 启用 DBLP（仅 CS 条目，默认关闭）
- `--enable-citation-cff` / `--disable-citation-cff` 启用/禁用 GitHub CITATION.cff（默认开启）
- `--high-conf` / `--mid-conf` 置信度门控阈值（默认 0.8/0.6）
- `--user-agent` 自定义 UA
- Fix：`--fix` / `--dry-run` / `--inplace` / `--aggressive`
- Autofix：`--autofix` / `--no-network` / `--min-conf` / `--autofix-scope` / `--fixed-bib` / `--changes-log` / `--fix-summary`
- `--latex-apostrophe` 将作者名中的 ’ 转为 `{\\textquoteright}`

退出码：若存在 ERROR 级问题则返回 1，否则 0，便于 CI。

## 输出

- `out/report.json`：结构化报告
- `out/report.csv`：摘要行（citekey、状态、问题等）
- 终端汇总：总数、OK/WARNING/ERROR、按错误类型计数、ERROR citekey 列表
- Fix/Autofix 额外输出：
  - `out/<name>.fixed.bib`（或原文件，若 `--inplace`）
  - `out/changes.jsonl` 变更日志（citekey、字段、old/new、来源、置信度、时间戳）
  - `out/fix_summary.md` 修复汇总

## 支持的主要错误类型

- 静态：`PARSE_ERROR`、`DUPLICATE_CITEKEY`、`MISSING_REQUIRED_FIELDS`、`BAD_YEAR`、`BAD_DOI_FORMAT`、`BAD_URL_FORMAT`、`SUSPICIOUS_METADATA`
- 联网：`DOI_NOT_FOUND`、`TITLE_MISMATCH`、`YEAR_MISMATCH`、`AUTHOR_MISMATCH`、`VENUE_MISMATCH`、`CANDIDATE_FOUND_NO_DOI`、`NOT_FOUND_ONLINE`
- 新增：`NOT_FOUND_ON_ARXIV`、`CITATION_CFF_MISSING`、`AMBIGUOUS_MATCH`、`LOW_CONFIDENCE_CANDIDATE`
- Blog-aware：`WEB_CITATION_NEEDS_URLDATE`、`WEB_TITLE_MISMATCH`、`WEB_AUTHOR_MISMATCH`、`WEB_DATE_MISMATCH`、`WEB_CITATION_HAS_FAKE_DOI`、`WEB_BIBTEX_AVAILABLE`

## 典型工作流

1. 从 Overleaf/Zotero 导出 `.bib`
2. `python -m bibcheck your.bib` 查看报告
3. 若存在明显错误，手工或回到参考管理工具修正
4. 需要自动补 DOI/元数据：`python -m bibcheck your.bib --fix`
5. 含研究博客/项目页，想自动对齐网页元数据：`python -m bibcheck your.bib --autofix --min-conf 0.85`
6. arXiv 预印本优先查 arXiv API，GitHub 软件条目优先读取 CITATION.cff，CS 论文可选 DBLP 兜底。

## 开发与测试

```bash
pytest
```

测试中所有在线请求均使用 `responses` mock，无需真实联网。

## 示例

`sample.bib` 包含：

- 正确 DOI 条目（ResNet）
- 明显错误条目（年/DOI/URL/pages）
- arXiv 需归一化/补 DOI
- OpenAI 研究博客条目（blog-aware 测试）

示例命令：

```bash
python -m bibcheck sample.bib
python -m bibcheck sample.bib --autofix --outdir out --min-conf 0.85
```
