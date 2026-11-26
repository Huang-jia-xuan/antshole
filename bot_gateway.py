import os
import subprocess
import time
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])
# 可替换为 claude -p 或其他 CLI Agent 命令
AGENT_CMD_PREFIX = ["aider", "--yes-always", "--no-auto-commits", "--model", "deepseek/deepseek-chat", "--message"]

tunnel_url = "尚未启动监控隧道"

def start_monitor_and_tunnel():
    """后台启动实验服务端与 Cloudflare 免费公网隧道"""
    global tunnel_url
    # 1. 重启你的多智能体实验服务（假设入口为 server.py，监听 8000 端口）
    subprocess.run(["pkill", "-f", "server.py"])
    subprocess.Popen(["python", "server.py"], stdout=open("server.log", "w"), stderr=subprocess.STDOUT)
    
    # 2. 启动 cloudflared 临时隧道将 8000 端口映射到公网 HTTPS
    subprocess.run(["pkill", "-f", "cloudflared"])
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:8000"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    # 捕获生成的随机 trycloudflare.com 链接
    for _ in range(30):
        line = proc.stdout.readline()
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if match:
            tunnel_url = match.group(0)
            break

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return  # 忽略非本人消息
    
    prompt = update.message.text
    await update.message.reply_text("⏳ 收到指令，云端 Agent 正在修改并验证代码...")

    # 调用无头 Agent 执行任务
    result = subprocess.run(
        AGENT_CMD_PREFIX + [prompt],
        capture_output=True, text=True, timeout=600
    )
    
    # 每次改完自动重启实验服务端并刷新监控链接
    start_monitor_and_tunnel()
    
    # 截取 Agent 执行摘要（控制长度避免超 Telegram 单条消息限制）
    summary = result.stdout[-1500:] if result.stdout else result.stderr[-1500:]
    reply = (
        f"✅ **任务执行完毕**\n\n"
        f"📊 **实时监控面板**：{tunnel_url}\n\n"
        f"📝 **执行摘要**：\n```\n{summary}\n```"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")

async def git_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送 /push 一键提交代码回 GitHub，方便回家后在本地电脑拉取跑长实验"""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", "chore: update via telegram agent"])
    res = subprocess.run(["git", "push"], capture_output=True, text=True)
    await update.message.reply_text(f"🚀 代码已同步至仓库：\n{res.stdout or res.stderr}")

if __name__ == "__main__":
    start_monitor_and_tunnel()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("push", git_sync))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
