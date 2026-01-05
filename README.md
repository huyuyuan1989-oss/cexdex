# 🔗 全鏈資金流向深度分析系統 v3.0

[![Chain Monitor](https://github.com/huyuyuan1989-oss/cexdex/actions/workflows/daily_monitor.yml/badge.svg)](https://github.com/huyuyuan1989-oss/cexdex/actions/workflows/daily_monitor.yml)
[![GitHub Pages](https://img.shields.io/badge/Reports-GitHub%20Pages-blue)](https://huyuyuan1989-oss.github.io/cexdex/)

**機構級加密貨幣資金流向監控平台**，整合 DEX + CEX 數據，提供實時市場洞察。

## 📊 線上報告

👉 **[點擊查看最新分析報告](https://huyuyuan1989-oss.github.io/cexdex/)**

---

## ✨ 核心功能

### 🌤️ 宏觀市場氣象站
- **Binance 現貨價格**：BTC / ETH / SOL 實時價格
- **資金費率監控**：判斷市場貪婪/恐慌情緒
- **風險評分 (0-100)**：整合多維度指標的市場風險指數

### 🌐 資金流向總覽
- **公鏈 TVL 追蹤**：30+ 主流公鏈的資金動態
- **資金分佈分析**：原生幣 / 穩定幣 / 個別代幣佔比
- **跨鏈資金遷移**：自動偵測資金跨鏈轉移

### 🚀 代幣深度分析
- **動能狀態判斷**：🚀 爆發 / 🧐 吸籌 / ⚠️ 出貨 / ❄️ 冷卻
- **市場寬度分析**：漲跌家數比例
- **敘事關鍵字提取**：自動識別 #AI / #Meme / #PolitiFi 等熱點

### 🛡️ 數據品質管控
- **刷量過濾**：排除 Turnover > 100x 的異常代幣
- **殭屍盤過濾**：過濾有量無價變動的對敲交易
- **多數據源交叉驗證**：DefiLlama + DEX Screener + Binance

---

## 🚀 快速開始

### 本地運行

```bash
# 1. 克隆專案
git clone https://github.com/huyuyuan1989-oss/cexdex.git
cd cexdex

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 執行分析
python full_chain_monitor.py
```

### GitHub Actions 自動執行

專案已配置 GitHub Actions，每 30 分鐘自動執行分析並更新報告。

---

## 📁 專案結構

```
cexdex/
├── .github/workflows/
│   └── daily_monitor.yml    # GitHub Actions 工作流
├── reports/                 # 生成的 HTML 報告
├── logs/                    # 執行日誌
├── full_chain_monitor.py    # 主程式
├── requirements.txt         # Python 依賴
├── index.html               # GitHub Pages 首頁
└── chain_data.db            # SQLite 歷史數據庫
```

---

## 📈 數據來源

| 數據源 | 用途 |
|--------|------|
| [DefiLlama](https://defillama.com/) | 公鏈 TVL、CEX 資產 |
| [DEX Screener](https://dexscreener.com/) | DEX 代幣數據、交易量 |
| [Binance API](https://api.binance.com/) | 現貨價格、資金費率 |

---

## 🔧 配置說明

### Discord 通知

在 GitHub Secrets 中設置 `DISCORD_WEBHOOK` 環境變數，即可接收 Discord 通知。

### 執行間隔

修改 `full_chain_monitor.py` 中的 `SCHEDULE_INTERVAL` 變數（秒）：
- `1800`：每 30 分鐘
- `3600`：每 1 小時
- `0`：單次執行

---

## 📊 風險評分說明

| 分數 | 等級 | 含義 |
|------|------|------|
| 80-100 | 🔴 極度過熱 | 追高風險極高 |
| 60-79 | 🟠 市場過熱 | 需謹慎操作 |
| 40-59 | 🟡 中性偏多 | 正常行情 |
| 25-39 | 🟢 市場健康 | 適合佈局 |
| 0-24 | 🔵 極度恐慌 | 可能是機會 |

---

## 📜 許可證

MIT License

---

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request！

---

**Made with ❤️ for Crypto Traders**
