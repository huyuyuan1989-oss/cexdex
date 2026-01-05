# ☁️ 全鏈資金流向監控系統 - 24H 雲端部署指南

這份指南將教你如何將此 Python 腳本部署到雲端伺服器 (VPS)，讓它 24 小時不間斷運行，**即使你關閉電腦也能持續工作**。

---

## 📋 方案選擇

要實現「不用開著電腦」，你需要一台雲端電腦 (VPS)。建議選擇：

1.  **DigitalOcean / Vultr / Linode** (最推薦，簡單好用)
    *   成本：約 $4 - $6 美金 / 月
    *   系統：Ubuntu 22.04 LTS (最穩定)

2.  **AWS EC2 / Google Cloud Free Tier** (免費但設置較複雜)
    *   AWS 提供一年免費 t2.micro 或 t3.micro
    *   Google Cloud e2-micro 提供永久免費額度 (特定區域)

---

## 🚀 部署步驟 (以 Ubuntu 為例)

### 步驟 1: 準備伺服器
購買 VPS 後，你會獲得一組 IP 地址、使用者名稱 (通常是 `root`) 和密碼。

### 步驟 2: 連線到伺服器
在你的電腦上，開啟命令提示字元 (CMD) 或 PowerShell (Windows)，或 Terminal (Mac)，輸入：
```bash
ssh root@<你的伺服器IP>
# 例如: ssh root@123.45.67.89
# 接著輸入密碼登入
```

### 步驟 3: 上傳代碼
你可以使用 SFTP 軟體 (如 FileZilla) 將此資料夾內的所有檔案上傳到伺服器的 `/root/chain_monitor` 目錄。

或者，如果你的代碼在 GitHub 上：
```bash
git clone <你的GitHub倉庫連結> chain_monitor
cd chain_monitor
```

### 步驟 4: 一鍵安裝腳本 (推薦)
我們準備了一個安裝腳本。在伺服器上執行以下指令：

1. 進入目錄 (假設你上傳到了 chain_monitor)
   ```bash
   cd chain_monitor
   ```

2. 建立並執行安裝腳本
   * 複製下方的 `setup_vps.sh` 內容到伺服器上，或者手動執行以下指令：

   ```bash
   # 更新系統
   apt update && apt upgrade -y
   
   # 安裝 Python 和 pip
   apt install python3 python3-pip python3-venv -y
   
   # 建立虛擬環境
   python3 -m venv venv
   source venv/bin/activate
   
   # 安裝依賴
   pip install -r requirements.txt
   
   # 設定權限
   chmod +x full_chain_monitor.py
   ```

### 步驟 5: 設定背景自動執行 (Systemd)

這是最重要的一步，讓程式在背景永遠執行，且當機後會自動重啟。

1. 建立服務文件：
   ```bash
   nano /etc/systemd/system/chain_monitor.service
   ```

2. 貼上以下內容 (請根據實際路徑修改)：
   ```ini
   [Unit]
   Description=Full Chain Money Flow Monitor
   After=network.target

   [Service]
   # 你的工作目錄
   WorkingDirectory=/root/chain_monitor
   # Python 執行檔路徑 (虛擬環境)
   ExecStart=/root/chain_monitor/venv/bin/python full_chain_monitor.py
   # 當機自動重啟
   Restart=always
   # 重啟間隔
   RestartSec=10
   # 用戶 (通常是 root)
   User=root

   [Install]
   WantedBy=multi-user.target
   ```
   *按 `Ctrl+O` 儲存，`Enter` 確認，然後 `Ctrl+X` 退出。*

3. 啟動服務：
   ```bash
   # 重新載入設定
   systemctl daemon-reload
   
   # 啟動監控
   systemctl start chain_monitor
   
   # 設定開機自動啟動
   systemctl enable chain_monitor
   ```

---

## 🛠️ 常用管理指令

- **查看運行狀態** (確認是否在跑):
  ```bash
  systemctl status chain_monitor
  ```

- **查看即時日誌** (看終端機輸出):
  ```bash
  journalctl -u chain_monitor -f
  ```

- **停止程式**:
  ```bash
  systemctl stop chain_monitor
  ```

- **重啟程式** (更新代碼後):
  ```bash
  systemctl restart chain_monitor
  ```

---

## ❓ 常見問題

**Q: 我的「長線潛力股」資料還在嗎？**
A: 是的！程式使用的是 SQLite 資料庫 (`chain_data.db`)。只要你不刪除這個檔案，資料就會一直保存在伺服器上，越積越準。

**Q: 產生的 HTML 報告要怎麼看？**
A: 既然跑在伺服器上，你可以安裝一個簡單的網頁伺服器來查看報告：
```bash
# 在 chain_monitor 目錄下執行
apt install nginx -y
rm /var/www/html/index.nginx-debian.html
ln -s /root/chain_monitor/reports /var/www/html/reports
```
之後你就可以在瀏覽器輸入 `http://<你的伺服器IP>/reports` 來查看所有生成的 HTML 報告了！

---
**祝您投資順利！ 🚀**
