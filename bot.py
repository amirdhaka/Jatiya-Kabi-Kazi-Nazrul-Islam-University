import requests
import asyncio
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)

# ----------- 1. KEEP ALIVE SERVER (For Render 24/7) -----------
app = Flask('')

@app.route('/')
def home():
    return "JKKNIU Bot is Online!"

def run():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

# ----------- 2. CONFIGURATION -----------
# আপনার টোকেনটি অটোমেটিক বসানো হয়েছে
BOT_TOKEN = "8469596986:AAEcEr4Bm-MIhzshNkQ3rO2t4sc84AktzmI"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
}

# ----------- 3. JKKNIU DATA SCRAPER -----------
def get_data(tid):
    url = f"https://billpay.sonalibank.com.bd/JKKNIU/Home/Voucher/{tid}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        
        data = {
            "Transaction ID": tid, "Fee Details": "", "Name": "", 
            "Reg No": "N/A", "Student Id": "N/A", "Mobile": "N/A", 
            "Amount(BDT)": "", "Date": "Not Found"
        }
        
        # টেবিল থেকে তথ্য সংগ্রহ
        rows = soup.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True).replace(":", "")
                val = cols[1].get_text(strip=True)
                
                if "Fee Details" in key: data["Fee Details"] = val
                elif "Name" in key: data["Name"] = val
                elif "Reg No" in key: data["Reg No"] = val
                elif "Student Id" in key: data["Student Id"] = val
                elif "Mobile" in key: data["Mobile"] = val
                elif "Amount" in key: data["Amount(BDT)"] = val
                elif "Date" in key: data["Date"] = val

        # তারিখ ফিক্স (পুরো পেজ স্ক্যান করে তারিখ বের করার লজিক)
        if data["Date"] == "Not Found":
            all_text = soup.find_all(string=lambda x: x and "Date" in x)
            for text in all_text:
                parent_text = text.parent.get_text(strip=True)
                if ":" in parent_text:
                    possible_date = parent_text.split(":")[-1].strip()
                    if len(possible_date) >= 8:
                        data["Date"] = possible_date
                        break

        return data
    except:
        return None

# ----------- 4. RESULT SENDER -----------
async def process_roll(update_or_query, data_list):
    final_text = ""
    unique_phones = []
    
    for i, data in enumerate(data_list, 1):
        phone = data["Mobile"]
        wa_phone = "880" + phone[1:] if (phone.startswith("0") and len(phone) >= 11) else phone
        
        final_text += (
            f"📄 JKKNIU Result {i}\n"
            f"<pre>\n"
            f"Transaction ID: {data['Transaction ID']}\n"
            f"Fee Details   : {data['Fee Details']}\n"
            f"Name          : {data['Name']}\n"
            f"Reg No        : {data['Reg No']}\n"
            f"Student Id    : {data['Student Id']}\n"
            f"Mobile        : {data['Mobile']}\n"
            f"Amount(BDT)   : {data['Amount(BDT)']}\n"
            f"Date          : {data['Date']}\n"
            f"</pre>\n\n"
        )
        
        if phone != "N/A" and wa_phone not in unique_phones:
            unique_phones.append(wa_phone)

    keyboard = []
    for ph in unique_phones:
        # বাটন থেকে নাম্বার সরিয়ে শুধু পরিষ্কার লেবেল রাখা হয়েছে
        keyboard.append([
            InlineKeyboardButton("📱 WhatsApp", url=f"https://wa.me/{ph}"),
            InlineKeyboardButton("📢 Telegram", url=f"https://t.me/{ph}")
        ])
    
    msg_source = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    await msg_source.reply_text(
        final_text, 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )

# ----------- 5. CORE SEARCH ENGINE -----------
async def run_search(update_or_query, context, start_r, end_r):
    rolls = list(range(start_r, end_r + 1))
    context.user_data["current_end"] = end_r
    
    msg_source = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    status_msg = await msg_source.reply_text("⏳ Searching JKKNIU Portal...")
    
    total_found = 0
    for i, roll in enumerate(rolls, 1):
        try:
            url = f"https://billpay.sonalibank.com.bd/JKKNIU/Home/Search?searchStr={roll}"
            r = requests.get(url, headers=headers, timeout=10)
            
            if "Details" in r.text:
                soup = BeautifulSoup(r.text, "html.parser")
                links = soup.select("a[href*='Voucher']")
                data_list = []
                for link in links:
                    tid = link['href'].split("/")[-1]
                    d = get_data(tid)
                    if d and d["Name"]: data_list.append(d)
                
                if data_list:
                    total_found += 1
                    await process_roll(update_or_query, data_list)

            await status_msg.edit_text(
                f"⏳ Scanning JKKNIU...\n"
                f"🔢 Roll/Reg: {roll}\n"
                f"📊 Found: {total_found}\n"
                f"✅ Progress: {i}/{len(rolls)}"
            )
        except: continue

    next_kb = [[InlineKeyboardButton("👉 Next 500?", callback_data="next_500")]]
    await msg_source.reply_text(f"✅ JKKNIU Scan Done!\n📊 Total: {total_found}", reply_markup=InlineKeyboardMarkup(next_kb))

# ----------- 6. HANDLERS -----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Start Search", callback_data="btn_ready")]]
    await update.message.reply_text("জাতীয় কবি কাজী নজরুল ইসলাম বিশ্ববিদ্যালয় ফি চেক বট শুরু করুন:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        if "-" in text:
            s, e = map(int, text.split("-"))
            await run_search(update, context, s, e)
        else:
            r = int(text)
            await run_search(update, context, r, r)
    except: pass

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "btn_ready":
        await query.message.reply_text("🚀 Ready for JKKNIU ID/Reg Number Search!")
    elif query.data == "next_500":
        last_end = context.user_data.get("current_end", 0)
        if last_end > 0:
            await run_search(query, context, last_end + 1, last_end + 500)

# ----------- 7. MAIN START -----------
if __name__ == "__main__":
    keep_alive()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ JKKNIU Final Bot is Online!")
    application.run_polling()
