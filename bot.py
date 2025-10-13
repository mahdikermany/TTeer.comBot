from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, JobQueue
import requests
import jdatetime
from datetime import datetime, timedelta
import logging
import re
import json
import os

# ================== تنظیمات اولیه ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "8221687298:AAFFX7UWVspNI8W-KThb_0VtDT_w2dffPIA"
ADMIN_USER_ID = 72046362
CHANNEL_ID = "@-1002317288060"

# ================== توابع کمکی ==================
def get_iran_time():
    iran_time = datetime.now() + timedelta(hours=3, minutes=30)
    jalali_date = jdatetime.datetime.fromgregorian(datetime=iran_time)
    persian_date = jalali_date.strftime("%Y%m%d")
    persian_time = jalali_date.strftime("%H:%M")
    persian_date_display = jalali_date.strftime("%Y/%m/%d")
    persian_time_full = jalali_date.strftime("%H%M%S")
    
    return persian_date, persian_time, persian_date_display, persian_time_full

# ================== مدیریت فایل‌ها و دیتابیس ==================
ADMIN_SETTINGS_FILE = "admin_settings.json"

def load_admin_settings():
    default_settings = {
        "order_notifications": True,
        "channel_interval": 30  # مدت زمان بین ارسال پیام‌ها به کانال (دقیقه)
    }
    
    if os.path.exists(ADMIN_SETTINGS_FILE):
        with open(ADMIN_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            saved_settings = json.load(f)
            # اضافه کردن کلیدهای جدید اگر وجود ندارند
            for key, value in default_settings.items():
                if key not in saved_settings:
                    saved_settings[key] = value
            return saved_settings
    return default_settings

def save_admin_settings(settings):
    with open(ADMIN_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

ADMIN_SETTINGS = load_admin_settings()

USERS_DB = {}
USER_STATS = {"total_users": 0, "users": {}}

def save_user(user_id, user_name):
    if user_id not in USER_STATS["users"]:
        persian_date, persian_time, _, _ = get_iran_time()
        USER_STATS["users"][user_id] = {
            "join_date": f"{persian_date} {persian_time}",
            "name": user_name
        }
        USER_STATS["total_users"] = len(USER_STATS["users"])

def is_user_authorized(user_id):
    if user_id in USERS_DB and USERS_DB[user_id]["verified"]:
        if USERS_DB[user_id]["auth_expiry"] > datetime.now():
            return True
        else:
            del USERS_DB[user_id]
    return False

# شمارنده سفارشات
ORDER_COUNTERS_FILE = "order_counters.json"

def load_order_counters():
    persian_date, _, _, _ = get_iran_time()
    
    if os.path.exists(ORDER_COUNTERS_FILE):
        with open(ORDER_COUNTERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            if "last_date" in data and data["last_date"] == persian_date:
                return data["counters"]
    
    return {"sell": 1000, "buy": 2000}

def save_order_counters():
    persian_date, _, _, _ = get_iran_time()
    data = {
        "last_date": persian_date,
        "counters": ORDER_COUNTERS
    }
    with open(ORDER_COUNTERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

ORDER_COUNTERS = load_order_counters()

SUBSCRIBE_CODES_FILE = "subscribe_codes.json"

def load_subscribe_codes():
    if os.path.exists(SUBSCRIBE_CODES_FILE):
        with open(SUBSCRIBE_CODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "123456": {"national_code": "1234567890", "active": True},
        "654321": {"national_code": "9876543210", "active": True},
        "789012": {"national_code": "1111111111", "active": True}
    }

def save_subscribe_codes():
    with open(SUBSCRIBE_CODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(SUBSCRIBE_CODES, f, ensure_ascii=False, indent=2)

SUBSCRIBE_CODES = load_subscribe_codes()

USER_STATES = {}
ADMIN_STATES = {}

# ================== تنظیمات شبکه‌ها و کیف پول‌ها ==================
NETWORK_FEES = {
    "ERC20": 7,
    "TRC20": 5, 
    "BEP20": 2,
    "Solana": 2
}

NETWORK_DISPLAY_NAMES = {
    "ERC20": "ERC20 (اتریوم)",
    "TRC20": "TRC20 (ترون)", 
    "BEP20": "BEP20 (بایننس)",
    "Solana": "Solana (سولانا)"
}

WALLET_FILE = "wallet_addresses.json"

def load_wallet_addresses():
    if os.path.exists(WALLET_FILE):
        with open(WALLET_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "ERC20": "0x65D2b7FfF0ad9d87B4FAe317e2580eB2e716DE24",
        "TRC20": "TUvQ6SdWNkj8q7auUegsj7hXADeMhtgExX",
        "BEP20": "0x65D2b7FfF0ad9d87B4FAe317e2580eB2e716DE24",
        "Solana": "DRhsBu1SKqGdL3sARusrR4YYqqrem4wq2JuDSGHaomxK"
    }

def save_wallet_addresses(wallet_addresses):
    with open(WALLET_FILE, 'w', encoding='utf-8') as f:
        json.dump(wallet_addresses, f, ensure_ascii=False, indent=2)

WALLET_ADDRESSES = load_wallet_addresses()

# ================== سیستم ارسال خودکار به کانال ==================
async def send_channel_price(context: ContextTypes.DEFAULT_TYPE):
    try:
        tether_price, gold_price, gold_ounce, gold_dollar_price = await get_accurate_prices()
        persian_date, persian_time, persian_date_display, _ = get_iran_time()
        
        tether_display = f"{tether_price:,}" if tether_price > 0 else "0"
        gold_display = f"{gold_price:,}" if gold_price > 0 else "0"
        gold_ounce_display = f"{gold_ounce:,}" if gold_ounce > 0 else "0"
        gold_dollar_display = f"{gold_dollar_price:,}" if gold_dollar_price > 0 else "0"
        
        message = f"""🟢 *قیمت لحظه‌ای تتر و طلا*

 ▫️ *نرخ تتر*                   `{tether_display}` تومان
▫️ *طلا 18 عیار*     `{gold_display}` تومان 
 ▫️ *انس جهانی*                `{gold_ounce_display}` دلار
 ▫️ *قیمت دلار طلا*       `{gold_dollar_display}` تومان

ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ
📅 {persian_date_display}
⏰ {persian_time}

🤖 [استفاده از ربات کامل](https://t.me/TTeer_com_bot)"""
        
        await context.bot.send_message(
            chat_id=CHANNEL_ID, 
            text=message, 
            parse_mode='Markdown'
        )
        logging.info(f"✅ قیمت به کانال {CHANNEL_ID} ارسال شد - فاصله: {ADMIN_SETTINGS['channel_interval']} دقیقه")
    except Exception as e:
        logging.error(f"❌ خطا در ارسال قیمت به کانال: {e}")

# ================== سیستم تأیید هویت ==================
async def request_subscription_code(update: Update, context: ContextTypes.DEFAULT_TYPE, service_type):
    user_id = update.message.from_user.id
    
    if is_user_authorized(user_id):
        if service_type == "buy":
            await show_buy_options(update, context)
        elif service_type == "sell":
            await show_sell_options(update, context)
        return
    
    USER_STATES[user_id] = {"waiting_for_subscribe_code": True, "service_type": service_type}
    
    await update.message.reply_text(
        "🔐 *برای تایید هویت*\n\n"
        "لطفاً کد اشتراک خود را وارد کنید:\n\n"
        "درصورت نداشتن کد اشتراک به پشتیبانی پیام دهید:\n"
        "📞 پشتیبانی: @TTeercom",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🟢 قیمت الان چند؟")]], resize_keyboard=True)
    )

async def verify_subscription_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code):
    user_id = update.message.from_user.id
    
    if code == "🟢 قیمت الان چند؟":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await price_command(update, context)
        return
    
    if code in SUBSCRIBE_CODES and SUBSCRIBE_CODES[code]["active"]:
        USER_STATES[user_id] = {
            "subscribe_code": code,
            "waiting_for_national_code": True,
            "service_type": USER_STATES[user_id]["service_type"]
        }
        await update.message.reply_text("✅ کد اشتراک تأیید شد!\n\nلطفاً کد ملی خود را وارد کنید:")
    else:
        await update.message.reply_text(
            "❌ کد اشتراک نامعتبر!\n\nلطفاً کد صحیح را وارد کنید یا برای بازگشت روی '🟢 قیمت الان چند؟' کلیک کنید.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🟢 قیمت الان چند؟")]], resize_keyboard=True)
        )

async def verify_national_code(update: Update, context: ContextTypes.DEFAULT_TYPE, national_code):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    if national_code == "🟢 قیمت الان چند؟":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await price_command(update, context)
        return
    
    if national_code.isdigit() and len(national_code) == 10:
        subscribe_code = USER_STATES[user_id]["subscribe_code"]
        
        if SUBSCRIBE_CODES[subscribe_code]["national_code"] == national_code:
            USERS_DB[user_id] = {
                "subscribe_code": subscribe_code,
                "national_code": national_code,
                "verified": True,
                "name": user_name,
                "auth_expiry": datetime.now() + timedelta(minutes=15)
            }
            
            service_type = USER_STATES[user_id]["service_type"]
            del USER_STATES[user_id]
            
            await update.message.reply_text(f"✅ تأیید هویت کامل شد!\n\nسلام {user_name} عزیز!", reply_markup=main_menu_keyboard())
            
            if service_type == "buy":
                await show_buy_options(update, context)
            elif service_type == "sell":
                await show_sell_options(update, context)
        else:
            await update.message.reply_text(
                "❌ کد ملی با اطلاعات ثبت شده مطابقت ندارد!\n\nلطفاً کد ملی صحیح را وارد کنید.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🟢 قیمت الان چند؟")]], resize_keyboard=True)
            )
    else:
        await update.message.reply_text(
            "❌ کد ملی نامعتبر! باید 10 رقم باشد.\n\nلطفاً کد ملی صحیح را وارد کنید.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🟢 قیمت الان چند؟")]], resize_keyboard=True)
        )

# ================== سیستم خرید ==================
async def show_buy_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    tether_price, _, _, _ = await get_accurate_prices()
    
    USER_STATES[user_id] = {
        "waiting_for_buy_amount": True,
        "service_type": "buy",
        "current_price": tether_price
    }
    
    await update.message.reply_text(
        f"🛒 *خرید تتر از ما*\n\n💰 قیمت فعلی خرید تتر: {tether_price:,} تومان\n\n"
        "لطفاً مبلغ مورد نظر را به تومان وارد کنید:\n\nمثال: 1000000\n\n"
        "یا از دکمه‌های زیر انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("5,000,000 تومان"), KeyboardButton("10,000,000 تومان")],
            [KeyboardButton("15,000,000 تومان"), KeyboardButton("20,000,000 تومان")],
            [KeyboardButton("🟢 قیمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, amount_text):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    current_price = user_state["current_price"]
    
    if amount_text == "🟢 قیمت الان چند؟":
        await price_command(update, context)
        return
    
    try:
        clean_amount = re.sub(r'[^\d]', '', amount_text)
        amount = int(clean_amount)
        
        if amount < 1000000:
            await update.message.reply_text(
                "❌ مبلغ بسیار کم!\n\nحداقل مبلغ خرید 1,000,000 تومان است.\n\nلطفاً مبلغ معتبر وارد کنید:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("5,000,000 تومان"), KeyboardButton("10,000,000 تومان")],
                    [KeyboardButton("15,000,000 تومان"), KeyboardButton("20,000,000 تومان")],
                    [KeyboardButton("🟢 قیمت الان چند؟")]
                ], resize_keyboard=True)
            )
            return
        
        tether_amount = amount / current_price
        
        USER_STATES[user_id] = {
            "waiting_for_network": True,
            "amount": amount,
            "tether_amount": round(tether_amount, 2),
            "current_price": current_price
        }
        
        await update.message.reply_text(
            f"✅ *خلاصه سفارش خرید*\n\n💰 مبلغ: {amount:,} تومان\n"
            f"🔢 تعداد تتر محاسبه شده: {tether_amount:.2f}\n"
            f"💵 قیمت هر تتر: {current_price:,} تومان\n\n"
            "آیا از سفارش خود اطمینان دارید?",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("✅ تأیید و ادامه"), KeyboardButton("❌ انصراف")],
                [KeyboardButton("🟢 قیمت الان چند؟")]
            ], resize_keyboard=True)
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ مبلغ نامعتبر!\n\nلطفاً مبلغ را به صورت عددی وارد کنید:\n\nمثال: 1000000",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("5,000,000 تومان"), KeyboardButton("10,000,000 تومان")],
                [KeyboardButton("15,000,000 تومان"), KeyboardButton("20,000,000 تومان")],
                [KeyboardButton("🟢 قیمت الان چند؟")]
            ], resize_keyboard=True)
        )

async def handle_network_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, network):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    tether_amount = user_state["tether_amount"]
    network_fee = NETWORK_FEES[network]
    final_tether_amount = tether_amount - network_fee
    
    USER_STATES[user_id] = {
        "waiting_for_wallet": True,
        "amount": user_state["amount"],
        "tether_amount": tether_amount,
        "final_tether_amount": round(final_tether_amount, 2),
        "current_price": user_state["current_price"],
        "selected_network": network,
        "network_fee": network_fee
    }
    
    await update.message.reply_text(
        f"🌐 **شبکه انتخاب شده: {NETWORK_DISPLAY_NAMES[network]}**\n\n"
        f"💰 کارمزد شبکه: {network_fee} تتر\n"
        f"▫️ تتر محاسبه شده: {tether_amount:.2f}\n"
        f"🔢 *تتر دریافتی شما*: {final_tether_amount:.2f} تتر\n\n"
        "*لطفاً آدرس کیف پول خود را ارسال کنید*:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ انصراف")]], resize_keyboard=True)
    )

async def handle_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE, wallet_address):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if wallet_address == "❌ انصراف":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await price_command(update, context)
        return
    
    USER_STATES[user_id]["wallet_address"] = wallet_address
    
    persian_date, persian_time, persian_date_display, persian_time_full = get_iran_time()
    tracking_code = f"{persian_date}{persian_time_full}-{user_id}"
    
    ORDER_COUNTERS["buy"] += 1
    save_order_counters()
    order_number = ORDER_COUNTERS["buy"]
    
    final_message = (
        f"🎉 *سفارش خرید شما ثبت شد* \n\n"
        f"💰  مبلغ واریز شما: `{user_state['amount']:,}` تومان\n"
        f"🔢 تعداد تتر دریافتی شما: `{user_state['final_tether_amount']:.2f}` تتر\n"
        f"💵 قیمت خرید: `{user_state['current_price']:,}` تومان\n"
        f"🌐 شبکه انتخابی شما: {NETWORK_DISPLAY_NAMES[user_state['selected_network']]}\n"
        f"💼 آدرس کیف پول شما:\n`{wallet_address}`\n\n"
        f"🆔 کد پیگیری:\n`{tracking_code}`\n\n"
        f"📅 {persian_date_display} - {persian_time}\n\n"
        "📞 **لطفاً این پیام را برای پشتیبانی ارسال کنید:**\n@TTeercom\n\n"
        "⏰ **توجه:** این سفارش تنها به مدت 10 دقیقه معتبر است و پس از آن قیمت ممکن است تغییر کند."
    )
    
    await update.message.reply_text(final_message, parse_mode='Markdown', reply_markup=main_menu_keyboard())
    
    if ADMIN_SETTINGS["order_notifications"]:
        try:
            admin_message = (
                f"🛒 *سفارش خرید #{order_number}* \n\n"
                f"👤 کاربر: {update.message.from_user.first_name}\n"
                f"🆔 کاربری: `{user_id}`\n"
                f"📞 تماس با کاربر: [کلیک کنید](tg://user?id={user_id})\n\n"
                f"💰 مبلغ دریافتی ما: {user_state['amount']:,} تومان\n"
                f"🔢 تتر پرداختی ما: {user_state['final_tether_amount']:.2f}\n"
                f"💵 قیمت: {user_state['current_price']:,} تومان\n"
                f"🌐 شبکه: {user_state['selected_network']}\n"
                f"💼 آدرس کیف پول مشتری:\n`{wallet_address}`\n\n"
                f"🆔 کد پیگیری: `{tracking_code}`"
            )
            
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"خطا در ارسال به ادمین: {e}")
    
    del USER_STATES[user_id]

# ================== سیستم فروش (با اطلاعات بانکی جدید) ==================
async def show_sell_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    tether_price, _, _, _ = await get_accurate_prices()
    sell_price = tether_price - 1500
    
    USER_STATES[user_id] = {
        "waiting_for_sell_amount": True,
        "service_type": "sell",
        "current_price": tether_price,
        "sell_price": sell_price
    }
    
    await update.message.reply_text(
        f"💵 *فروش تتر به ما* \n\n💰 قیمت فعلی خرید تتر: {tether_price:,} تومان\n"
        f"💰 *قیمت فعلی فروش تتر* : *{sell_price:,}* *تومان* \n\n"
        "لطفاً تعداد تتر مورد نظر را وارد کنید:\n\nمثال: 10\n\n"
        "یا از دکمه‌های زیر انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("10 تتر"), KeyboardButton("20 تتر")],
            [KeyboardButton("50 تتر"), KeyboardButton("100 تتر")],
            [KeyboardButton("🟢 قیمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_sell_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, amount_text):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    sell_price = user_state["sell_price"]
    
    if amount_text == "🟢 قیمت الان چند؟":
        await price_command(update, context)
        return
    
    try:
        clean_amount = re.sub(r'[^\d]', '', amount_text)
        tether_amount = float(clean_amount)
        
        if tether_amount < 1:
            await update.message.reply_text(
                "❌ تعداد بسیار کم!\n\nحداقل تعداد فروش 1 تتر است.\n\nلطفاً تعداد معتبر وارد کنید:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("10 تتر"), KeyboardButton("20 تتر")],
                    [KeyboardButton("50 تتر"), KeyboardButton("100 تتر")],
                    [KeyboardButton("🟢 قیمت الان چند؟")]
                ], resize_keyboard=True)
            )
            return
        
        amount = int(tether_amount * sell_price)
        
        USER_STATES[user_id] = {
            "waiting_for_sell_network": True,
            "tether_amount": tether_amount,
            "amount": amount,
            "sell_price": sell_price
        }
        
        await update.message.reply_text(
            f"✅ *خلاصه سفارش فروش* \n\n🔢 *تعداد تتر فروشی شما:*  {tether_amount}\n"
            f"💰 مبلغ دریافتی شما: *{amount:,}* تومان\n\n"
            "آیا از سفارش خود اطمینان دارید?",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("✅ تأیید و ادامه"), KeyboardButton("❌ انصراف")],
                [KeyboardButton("🟢 قیمت الان چند؟")]
            ], resize_keyboard=True)
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ تعداد نامعتبر!\n\nلطفاً تعداد تتر را به صورت عددی وارد کنید:\n\nمثال: 10",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("10 تتر"), KeyboardButton("20 تتر")],
                [KeyboardButton("50 تتر"), KeyboardButton("100 تتر")],
                [KeyboardButton("🟢 قیمت الان چند؟")]
            ], resize_keyboard=True)
        )

async def handle_sell_network_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, network):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    USER_STATES[user_id] = {
        "waiting_for_card_number": True,
        "tether_amount": user_state["tether_amount"],
        "amount": user_state["amount"],
        "sell_price": user_state["sell_price"],
        "selected_network": network
    }
    
    await update.message.reply_text(
        "💳 *لطفا شماره کارت خود را جهت واریز وجه وارد کنید* \n\n"
        "⚠️⚠️  در صورت اینکه شماره کارت به نام غیر باشد وجه واریز نخواهد شد",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("لازم نیست")],
            [KeyboardButton("🟢 قیمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE, card_number):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if card_number == "🟢 قیمت الان چند؟":
        await price_command(update, context)
        return
    
    if card_number == "لازم نیست":
        card_number = ""
    
    USER_STATES[user_id] = {
        "waiting_for_account_number": True,
        "tether_amount": user_state["tether_amount"],
        "amount": user_state["amount"],
        "sell_price": user_state["sell_price"],
        "selected_network": user_state["selected_network"],
        "card_number": card_number
    }
    
    await update.message.reply_text(
        "🏦 *لطفاً شماره حساب خود را وارد کنید* ",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("لازم نیست")],
            [KeyboardButton("🟢 قیمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_account_number(update: Update, context: ContextTypes.DEFAULT_TYPE, account_number):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if account_number == "🟢 قیمت الان چند؟":
        await price_command(update, context)
        return
    
    if account_number == "لازم نیست":
        account_number = ""
    
    USER_STATES[user_id] = {
        "waiting_for_sheba_number": True,
        "tether_amount": user_state["tether_amount"],
        "amount": user_state["amount"],
        "sell_price": user_state["sell_price"],
        "selected_network": user_state["selected_network"],
        "card_number": user_state["card_number"],
        "account_number": account_number
    }
    
    await update.message.reply_text(
        "🌐 **لطفاً شماره شبا خود را وارد کنید**\n\n"
        "💡💡 نیازی به وارد کردن IR نیست، فقط اعداد را وارد کنید",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("لازم نیست")],
            [KeyboardButton("🟢 قیمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_sheba_number(update: Update, context: ContextTypes.DEFAULT_TYPE, sheba_number):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if sheba_number == "🟢 قیمت الان چند؟":
        await price_command(update, context)
        return
    
    if sheba_number == "لازم نیست":
        sheba_number = ""
        sheba_display = ""
    else:
        # اضافه کردن IR به شماره شبا اگر وجود ندارد
        sheba_display = sheba_number.upper()
        if not sheba_display.startswith('IR'):
            sheba_display = f'IR{sheba_display}'
    
    USER_STATES[user_id] = {
        "waiting_for_account_holder": True,
        "tether_amount": user_state["tether_amount"],
        "amount": user_state["amount"],
        "sell_price": user_state["sell_price"],
        "selected_network": user_state["selected_network"],
        "card_number": user_state["card_number"],
        "account_number": user_state["account_number"],
        "sheba_number": sheba_number,
        "sheba_display": sheba_display
    }
    
    await update.message.reply_text(
        "👤 *لطفاً نام دارنده حساب را وارد کنید* \n\n"
        "⚠️هشدار مهم⚠️\n  حساب باید به نام خودتان باشد، در غیر این صورت وجه واریز نخواهد شد",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ انصراف")]], resize_keyboard=True)
    )

async def handle_account_holder(update: Update, context: ContextTypes.DEFAULT_TYPE, account_holder):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if account_holder == "❌ انصراف":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await price_command(update, context)
        return
    
    wallet_address = WALLET_ADDRESSES.get(user_state["selected_network"], "")
    
    if not wallet_address:
        await update.message.reply_text(
            "❌ آدرس کیف پول برای این شبکه تنظیم نشده است.\n\nلطفاً با پشتیبانی تماس بگیرید.",
            reply_markup=main_menu_keyboard()
        )
        del USER_STATES[user_id]
        return
    
    persian_date, persian_time, persian_date_display, persian_time_full = get_iran_time()
    tracking_code = f"{persian_date}{persian_time_full}-{user_id}"
    
    ORDER_COUNTERS["sell"] += 1
    save_order_counters()
    order_number = ORDER_COUNTERS["sell"]
    
    # ساخت بخش اطلاعات بانکی به صورت شرطی
    bank_info = "💳 **اطلاعات بانکی شما:**\n"
    if user_state['card_number']:
        bank_info += f"• شماره کارت:\n`{user_state['card_number']}`\n\n"
    if user_state['account_number']:
        bank_info += f"• شماره حساب:\n`{user_state['account_number']}`\n\n"
    if user_state['sheba_display']:
        bank_info += f"• شماره شبا:\n`{user_state['sheba_display']}`\n\n"
    bank_info += f"• نام دارنده حساب:\n`{account_holder}`\n\n"
    
    final_message = (
        f"🎉 *سفارش فروش شما ثبت شد* \n\n"
        f"🔢 تعداد تتری که باید واریز کنید: `{user_state['tether_amount']}`\n"
        f"🌐 شبکه: {NETWORK_DISPLAY_NAMES[user_state['selected_network']]}\n\n"
        f"💼 آدرس کیف پول برای واریز:\n`{wallet_address}`\n\n"
        "📞 **بعد از واریزی، فیش واریزی تتر را برای پشتیبان ارسال نمایید:**\n@TTeercom\n"
        f"ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ\n\n"
        f"💰 *مبلغ دریافتی شما* : `{user_state['amount']:,}` تومان\n"
        f"💵 قیمت فروش: `{user_state['sell_price']:,}` تومان\n\n"
        f"{bank_info}"
        f"🆔 کد پیگیری:\n`{tracking_code}`\n"
        f"📅 {persian_date_display} - {persian_time}\n\n"
        "⏰ **توجه مهم:** این فرآیند باید حداکثر تا 10 دقیقه از زمان ثبت انجام شود."
    )
    
    await update.message.reply_text(final_message, parse_mode='Markdown', reply_markup=main_menu_keyboard())
    
    if ADMIN_SETTINGS["order_notifications"]:
        try:
            # ساخت بخش اطلاعات بانکی برای ادمین
            admin_bank_info = "💳 **اطلاعات بانکی:**\n"
            if user_state['card_number']:
                admin_bank_info += f"• شماره کارت: `{user_state['card_number']}`\n"
            if user_state['account_number']:
                admin_bank_info += f"• شماره حساب: `{user_state['account_number']}`\n"
            if user_state['sheba_display']:
                admin_bank_info += f"• شماره شبا: `{user_state['sheba_display']}`\n"
            admin_bank_info += f"• نام دارنده حساب: `{account_holder}`\n\n"
            
            admin_message = (
                f"💵 **سفارش فروش #{order_number}**\n\n"
                f"👤 کاربر: {update.message.from_user.first_name}\n"
                f"🆔 کاربری: `{user_id}`\n"
                f"📞 تماس با کاربر: [کلیک کنید](tg://user?id={user_id})\n\n"
                f"🔢 تتر دریافتی: {user_state['tether_amount']}\n"
                f"💰 *مبلغی پرداختی ما:* `{user_state['amount']:,}` *تومان*\n"
                f"💵 قیمت فروش: {user_state['sell_price']:,} تومان\n"
                f"🌐 شبکه: {user_state['selected_network']}\n\n"
                f"{admin_bank_info}"
                f"🆔 کد پیگیری: `{tracking_code}`"
            )
            
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"خطا در ارسال به ادمین: {e}")
    
    del USER_STATES[user_id]

# ================== سیستم دریافت قیمت‌ها ==================
async def get_accurate_prices():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    tether_price = 0
    try:
        response = requests.get('https://api.kifpool.app/api/spot/price/paginated?offset=0&limit=25', headers=headers, timeout=10)
        data = response.json()
        if 'data' in data:
            for item in data['data']:
                if item.get('symbol') == 'USDT':
                    tether_price = int(item.get('priceSellIRT', 0))
                    break
    except Exception as e:
        logging.error(f"❌ خطا در دریافت قیمت تتر: {e}")

    gold_price = 0
    try:
        response = requests.get('https://milli.gold/api/v1/public/milli-price/external', headers=headers, timeout=10)
        data = response.json()
        if 'price18' in data:
            gold_price = int(data['price18']) * 100
    except Exception as e:
        logging.error(f"❌ خطا در دریافت قیمت طلا: {e}")

    gold_ounce = 0
    try:
        response = requests.get('https://data-asg.goldprice.org/dbXRates/USD', headers=headers, timeout=10)
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            gold_ounce = int(float(data['items'][0]['xauPrice']))
    except Exception as e:
        logging.error(f"❌ خطا در دریافت انس جهانی: {e}")

    gold_dollar_price = 0
    if gold_price > 0 and gold_ounce > 0:
        try:
            gold_dollar_price = int((gold_price * 31.1035) / (gold_ounce * 0.75))
        except:
            gold_dollar_price = 0

    return tether_price, gold_price, gold_ounce, gold_dollar_price

# ================== دستورات کاربری ==================
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in USER_STATES:
        del USER_STATES[user_id]
    
    wait_msg = await update.message.reply_text("🔄 در حال دریافت آخرین قیمت‌ها...")
    tether_price, gold_price, gold_ounce, gold_dollar_price = await get_accurate_prices()
    persian_date, persian_time, persian_date_display, _ = get_iran_time()
    
    tether_display = f"{tether_price:,}" if tether_price > 0 else "0"
    gold_display = f"{gold_price:,}" if gold_price > 0 else "0"
    gold_ounce_display = f"{gold_ounce:,}" if gold_ounce > 0 else "0"
    gold_dollar_display = f"{gold_dollar_price:,}" if gold_dollar_price > 0 else "0"
    
    message = f"""🟢 *قیمت الان...*

 ▫️ *نرخ تتر*                   `{tether_display}` تومان
▫️ *طلا 18 عیار*     `{gold_display}` تومان 
 ▫️ *انس جهانی*                `{gold_ounce_display}` دلار
 ▫️ *قیمت دلار طلا*       `{gold_dollar_display}` تومان

ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ
📅{persian_date_display}
⏰{persian_time}

🤖 [قیمت الان چند؟](https://t.me/TTeer_com_bot)"""
    
    await wait_msg.delete()
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=main_menu_keyboard())

def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("🟢 قیمت لحظه ای تتر و طلا")],
        [KeyboardButton("🛒 خرید تتر از ما"), KeyboardButton("💵 فروش تتر به ما")],
        [KeyboardButton("📖 راهنما"), KeyboardButton("📢 کانال ما")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    save_user(user_id, user_name)
    
    welcome_message = f"""👋 سلام {user_name}!
به ربات تتردات کام خوش آمدید!

💡 **امکانات ربات:**
• دریافت قیمت لحظه‌ای تتر و طلا
• خرید و فروش امن تتر
• پشتیبانی 24 ساعته

📢 **کانال اطلاع‌رسانی ما:**
@TTeer_com

لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"""
    
    await update.message.reply_text(welcome_message, reply_markup=main_menu_keyboard())

# ================== دستورات مدیریت کانال ==================
async def set_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📝 **دستور تنظیم فاصله ارسال به کانال:**\n\nUsage: /setinterval <دقیقه>\n\nمثال:\n/setinterval 30\n/setinterval 15"
        )
        return
    
    try:
        interval = int(context.args[0])
        if interval < 5:
            await update.message.reply_text("❌ فاصله ارسال نمی‌تواند کمتر از 5 دقیقه باشد!")
            return
        
        ADMIN_SETTINGS["channel_interval"] = interval
        save_admin_settings(ADMIN_SETTINGS)
        
        # توقف و راه‌اندازی مجدد job با فاصله جدید
        job_queue = context.application.job_queue
        if job_queue:
            # حذف jobهای قبلی
            for job in job_queue.jobs():
                if job.name == "channel_price_job":
                    job.schedule_removal()
            
            # ایجاد job جدید با فاصله جدید
            job_queue.run_repeating(
                send_channel_price,
                interval=interval * 60,  # تبدیل به ثانیه
                first=10,  # 10 ثانیه بعد
                name="channel_price_job"
            )
        
        await update.message.reply_text(f"✅ فاصله ارسال به کانال به {interval} دقیقه تنظیم شد!")
        
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر! لطفاً یک عدد وارد کنید.")

async def send_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    try:
        await send_channel_price(context)
        await update.message.reply_text("✅ قیمت با موفقیت به کانال ارسال شد!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال به کانال: {e}")

async def channel_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    try:
        # بررسی وضعیت کانال
        channel_info = await context.bot.get_chat(CHANNEL_ID)
        channel_members = await context.bot.get_chat_members_count(CHANNEL_ID)
        
        status_message = f"""
📊 **وضعیت کانال:**

📢 نام کانال: {channel_info.title}
👥 تعداد اعضا: {channel_members}
⏰ فاصله ارسال: {ADMIN_SETTINGS['channel_interval']} دقیقه
🔄 وضعیت ارسال خودکار: ✅ فعال

💡 **دستورات مدیریت کانال:**
• /setinterval <دقیقه> - تنظیم فاصله ارسال
• /sendnow - ارسال فوری قیمت
• /channelstatus - نمایش این وضعیت
"""
        await update.message.reply_text(status_message)
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت وضعیت کانال: {e}")

# ================== دستورات مدیریتی ==================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id == ADMIN_USER_ID:
        await admin_help_command(update, context)
        return
    
    help_text = """
📖 **راهنمای ربات تتردات کام:**

🛒 **خرید تتر:**
1. انتخاب گزینه "خرید تتر از ما"
2. وارد کردن کد اشتراک و کد ملی
3. انتخاب مبلغ مورد نظر
4. انتخاب شبکه و وارد کردن آدرس کیف پول

💵 **فروش تتر:**
1. انتخاب گزینه "فروش تتر به ما" 
2. وارد کردن کد اشتراک و کد ملی
3. وارد کردن تعداد تتر
4. انتخاب شبکه برای واریز

💰 **سایر امکانات:**
• دریافت قیمت لحظه‌ای تتر و طلا
• پشتیبانی 24 ساعته

📞 پشتیبانی:\n @TTeercom
📢 کانال:\n @TTeer_com
"""
    await update.message.reply_text(help_text, reply_markup=main_menu_keyboard())

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    notifications_status = "✅ روشن" if ADMIN_SETTINGS["order_notifications"] else "❌ خاموش"
    interval_status = f"{ADMIN_SETTINGS['channel_interval']} دقیقه"
    
    help_text = f"""
🛠️ **دستورات مدیریتی ربات**

📊 **آمار و مدیریت:**
• /stats - نمایش آمار کاربران
• /broadcast <پیام> - ارسال پیام به همه کاربران
• /togglenotifications - تغییر وضعیت اطلاع‌رسانی ({notifications_status})

📢 **مدیریت کانال:**
• /setinterval <دقیقه> - تنظیم فاصله ارسال به کانال ({interval_status})
• /sendnow - ارسال فوری قیمت به کانال
• /channelstatus - نمایش وضعیت کانال

💰 **مدیریت کیف پول:**
• /setwallet <شبکه> <آدرس> - تنظیم آدرس کیف پول
• /wallets - نمایش آدرس‌های فعلی

🔐 **مدیریت کدهای اشتراک:**
• /addcode <کد> <کد_ملی> - اضافه کردن کد اشتراک
• /removecode <کد> - حذف کد اشتراک
• /listcodes - نمایش همه کدها
• /togglecode <کد> - فعال/غیرفعال کردن کد

🔧 **سایر دستورات:**
• /admin - نمایش این راهنما
• /help - نمایش راهنمای کاربری

📝 **مثال‌ها:**
• /setwallet TRC20 TUvQ6SdWNkj8q7auUegsj7hXADeMhtgExX
• /broadcast اطلاعیه جدید
• /addcode 123456 1234567890
• /setinterval 15
• /sendnow
"""
    await update.message.reply_text(help_text)

async def toggle_notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    ADMIN_SETTINGS["order_notifications"] = not ADMIN_SETTINGS["order_notifications"]
    save_admin_settings(ADMIN_SETTINGS)
    
    status = "✅ روشن" if ADMIN_SETTINGS["order_notifications"] else "❌ خاموش"
    await update.message.reply_text(f"✅ وضعیت اطلاع‌رسانی سفارشات به {status} تغییر کرد.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    total_users = USER_STATS["total_users"]
    active_users = len([user for user in USERS_DB if USERS_DB[user]["verified"]])
    
    stats_text = f"""
📊 **آمار ربات**

👥 تعداد کل کاربران: {total_users}
✅ کاربران فعال: {active_users}
🔄 کاربران در حال تراکنش: {len(USER_STATES)}
⏰ فاصله ارسال به کانال: {ADMIN_SETTINGS['channel_interval']} دقیقه

📈 **آخرین کاربران:**
"""
    
    user_count = 0
    for user_id, user_data in list(USER_STATS["users"].items())[-5:]:
        user_count += 1
        stats_text += f"\n{user_count}. {user_data['name']} - {user_data['join_date']}"
    
    await update.message.reply_text(stats_text)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args:
        await update.message.reply_text("📢 **دستور ارسال پیام همگانی:**\n\nUsage: /broadcast <پیام>\n\nمثال:\n/broadcast اطلاعیه مهم")
        return
    
    message = ' '.join(context.args)
    users_count = 0
    failed_count = 0
    
    for user_id in USER_STATS["users"]:
        try:
            await context.bot.send_message(chat_id=user_id, text=f"📢 **پیام همگانی:**\n\n{message}")
            users_count += 1
        except:
            failed_count += 1
    
    await update.message.reply_text(f"✅ ارسال پیام همگانی انجام شد:\n\n✅ موفق: {users_count} کاربر\n❌ ناموفق: {failed_count} کاربر")

async def set_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 **دستور تنظیم آدرس کیف پول:**\n\nUsage: /setwallet <network> <address>\n\n"
            "🌐 شبکه‌های موجود:\n- ERC20\n- TRC20\n- BEP20\n- Solana\n\n"
            "مثال:\n/setwallet TRC20 TUvQ6SdWNkj8q7auUegsj7hXADeMhtgExX"
        )
        return
    
    network = context.args[0].upper()
    address = ' '.join(context.args[1:])
    
    if network not in NETWORK_FEES:
        await update.message.reply_text("❌ شبکه نامعتبر!\n\nشبکه‌های معتبر:\n- ERC20\n- TRC20\n- BEP20\n- Solana")
        return
    
    WALLET_ADDRESSES[network] = address
    save_wallet_addresses(WALLET_ADDRESSES)
    
    await update.message.reply_text(
        f"✅ آدرس کیف پول برای شبکه {NETWORK_DISPLAY_NAMES[network]} با موفقیت تنظیم شد!\n\nآدرس جدید:\n`{address}`",
        parse_mode='Markdown'
    )

async def show_wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    message = "💰 **آدرس‌های کیف پول فعلی:**\n\n"
    for network, address in WALLET_ADDRESSES.items():
        display_name = NETWORK_DISPLAY_NAMES.get(network, network)
        message += f"🌐 {display_name}:\n`{address}`\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def add_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 **دستور اضافه کردن کد اشتراک:**\n\nUsage: /addcode <کد> <کد_ملی>\n\nمثال:\n/addcode 123456 1234567890"
        )
        return
    
    code = context.args[0]
    national_code = context.args[1]
    
    if code in SUBSCRIBE_CODES:
        await update.message.reply_text(f"❌ کد اشتراک '{code}' از قبل وجود دارد!")
        return
    
    SUBSCRIBE_CODES[code] = {"national_code": national_code, "active": True}
    save_subscribe_codes()
    
    await update.message.reply_text(f"✅ کد اشتراک '{code}' با موفقیت اضافه شد!\n\nکد ملی مرتبط: {national_code}")

async def remove_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args:
        await update.message.reply_text("📝 **دستور حذف کد اشتراک:**\n\nUsage: /removecode <کد>\n\nمثال:\n/removecode 123456")
        return
    
    code = context.args[0]
    if code not in SUBSCRIBE_CODES:
        await update.message.reply_text(f"❌ کد اشتراک '{code}' وجود ندارد!")
        return
    
    del SUBSCRIBE_CODES[code]
    save_subscribe_codes()
    await update.message.reply_text(f"✅ کد اشتراک '{code}' با موفقیت حذف شد!")

async def list_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not SUBSCRIBE_CODES:
        await update.message.reply_text("❌ هیچ کد اشتراکی وجود ندارد!")
        return
    
    message = "📋 **لیست کدهای اشتراک:**\n\n"
    for code, data in SUBSCRIBE_CODES.items():
        status = "✅ فعال" if data["active"] else "❌ غیرفعال"
        message += f"🔸 کد: `{code}`\n   کد ملی: `{data['national_code']}`\n   وضعیت: {status}\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def toggle_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ دسترسی denied!")
        return
    
    if not context.args:
        await update.message.reply_text("📝 **دستور فعال/غیرفعال کردن کد اشتراک:**\n\nUsage: /togglecode <کد>\n\nمثال:\n/togglecode 123456")
        return
    
    code = context.args[0]
    if code not in SUBSCRIBE_CODES:
        await update.message.reply_text(f"❌ کد اشتراک '{code}' وجود ندارد!")
        return
    
    SUBSCRIBE_CODES[code]["active"] = not SUBSCRIBE_CODES[code]["active"]
    save_subscribe_codes()
    status = "فعال" if SUBSCRIBE_CODES[code]["active"] else "غیرفعال"
    await update.message.reply_text(f"✅ کد اشتراک '{code}' با موفقیت {status} شد!")

# ================== هندلر اصلی پیام‌ها ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if user_id in USER_STATES:
        state = USER_STATES[user_id]
        
        if state.get("waiting_for_subscribe_code"):
            await verify_subscription_code(update, context, text)
            return
        
        elif state.get("waiting_for_national_code"):
            await verify_national_code(update, context, text)
            return
        
        elif state.get("waiting_for_buy_amount"):
            await handle_buy_amount(update, context, text)
            return
        
        elif state.get("waiting_for_sell_amount"):
            await handle_sell_amount(update, context, text)
            return
        
        elif state.get("waiting_for_network"):
            if text == "✅ تأیید و ادامه":
                await update.message.reply_text(
                    "🌐 **لطفاً شبکه مورد نظر را انتخاب کنید:**\n\n💰 **کارمزد شبکه‌ها:**\n"
                    "• ERC20 (اتریوم) - 7 تتر\n• TRC20 (ترون) - 5 تتر\n"
                    "• BEP20 (بایننس) - 2 تتر\n• Solana (سولانا) - 2 تتر",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("ERC20 (اتریوم)"), KeyboardButton("TRC20 (ترون)")],
                        [KeyboardButton("BEP20 (بایننس)"), KeyboardButton("Solana (سولانا)")],
                        [KeyboardButton("🟢 قیمت الان چند؟")]
                    ], resize_keyboard=True)
                )
                return
            elif text in ["ERC20 (اتریوم)", "TRC20 (ترون)", "BEP20 (بایننس)", "Solana (سولانا)"]:
                network_map = {
                    "ERC20 (اتریوم)": "ERC20", "TRC20 (ترون)": "TRC20", 
                    "BEP20 (بایننس)": "BEP20", "Solana (سولانا)": "Solana"
                }
                network = network_map[text]
                await handle_network_selection(update, context, network)
                return
            elif text in ["❌ انصراف", "🟢 قیمت الان چند؟"]:
                del USER_STATES[user_id]
                await price_command(update, context)
                return
        
        elif state.get("waiting_for_wallet"):
            if text == "❌ انصراف":
                if user_id in USER_STATES:
                    del USER_STATES[user_id]
                await price_command(update, context)
                return
            else:
                await handle_wallet_address(update, context, text)
                return
        
        elif state.get("waiting_for_sell_network"):
            if text == "✅ تأیید و ادامه":
                await update.message.reply_text(
                    "🌐 لطفاً شبکه مورد نظر برای واریز تتر را انتخاب کنید:",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("ERC20 (اتریوم)"), KeyboardButton("TRC20 (ترون)")],
                        [KeyboardButton("BEP20 (بایننس)"), KeyboardButton("Solana (سولانا)")],
                        [KeyboardButton("🟢 قیمت الان چند؟")]
                    ], resize_keyboard=True)
                )
                return
            elif text in ["ERC20 (اتریوم)", "TRC20 (ترون)", "BEP20 (بایننس)", "Solana (سولانا)"]:
                network_map = {
                    "ERC20 (اتریوم)": "ERC20", "TRC20 (ترون)": "TRC20", 
                    "BEP20 (بایننس)": "BEP20", "Solana (سولانا)": "Solana"
                }
                network = network_map[text]
                await handle_sell_network_selection(update, context, network)
                return
            elif text in ["❌ انصراف", "🟢 قیمت الان چند؟"]:
                del USER_STATES[user_id]
                await price_command(update, context)
                return
        
        # حالت جدید: انتظار برای شماره کارت
        elif state.get("waiting_for_card_number"):
            if text == "🟢 قیمت الان چند؟":
                await price_command(update, context)
                return
            else:
                await handle_card_number(update, context, text)
                return
        
        # حالت جدید: انتظار برای شماره حساب
        elif state.get("waiting_for_account_number"):
            if text == "🟢 قیمت الان چند؟":
                await price_command(update, context)
                return
            else:
                await handle_account_number(update, context, text)
                return
        
        # حالت جدید: انتظار برای شماره شبا
        elif state.get("waiting_for_sheba_number"):
            if text == "🟢 قیمت الان چند؟":
                await price_command(update, context)
                return
            else:
                await handle_sheba_number(update, context, text)
                return
        
        # حالت جدید: انتظار برای نام دارنده حساب
        elif state.get("waiting_for_account_holder"):
            if text == "❌ انصراف":
                if user_id in USER_STATES:
                    del USER_STATES[user_id]
                await price_command(update, context)
                return
            else:
                await handle_account_holder(update, context, text)
                return
    
    if text == "🟢 قیمت لحظه ای تتر و طلا":
        await price_command(update, context)
    elif text == "🛒 خرید تتر از ما":
        await request_subscription_code(update, context, "buy")
    elif text == "💵 فروش تتر به ما":
        await request_subscription_code(update, context, "sell")
    elif text == "📢 کانال ما":
        await update.message.reply_text(
            "📢 **کانال اطلاع‌رسانی ما:**\n\n👉 @TTeer_com\n\n✅ قیمت‌های لحظه‌ای\n✅ اخبار و اطلاعیه‌ها",
            reply_markup=main_menu_keyboard()
        )
    elif text == "📖 راهنما":
        await help_command(update, context)
    elif text == "🟢 قیمت الان چند؟":
        await price_command(update, context)
    else:
        await update.message.reply_text("❌ دستور نامعتبر\nلطفاً از دکمه‌های زیر استفاده کنید:", reply_markup=main_menu_keyboard())

# ================== اجرای ربات ==================
def main():
    print("🚀 ربات تتردات کام با سیستم خرید و فروش پیشرفته فعال شد...")
    application = Application.builder().token(TOKEN).build()
    
    # تنظیم JobQueue برای ارسال خودکار به کانال
    job_queue = application.job_queue
    if job_queue:
        # اطمینان از وجود کلید channel_interval
        if "channel_interval" not in ADMIN_SETTINGS:
            ADMIN_SETTINGS["channel_interval"] = 30
            save_admin_settings(ADMIN_SETTINGS)
            
        interval_seconds = ADMIN_SETTINGS["channel_interval"] * 60
        job_queue.run_repeating(
            send_channel_price,
            interval=interval_seconds,
            first=10,  # 10 ثانیه بعد از راه‌اندازی
            name="channel_price_job"
        )
        print(f"✅ سیستم ارسال خودکار به کانال فعال شد - فاصله: {ADMIN_SETTINGS['channel_interval']} دقیقه")
    
    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_help_command))
    application.add_handler(CommandHandler("togglenotifications", toggle_notifications_command))
    application.add_handler(CommandHandler("setwallet", set_wallet_command))
    application.add_handler(CommandHandler("wallets", show_wallets_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addcode", add_code_command))
    application.add_handler(CommandHandler("removecode", remove_code_command))
    application.add_handler(CommandHandler("listcodes", list_codes_command))
    application.add_handler(CommandHandler("togglecode", toggle_code_command))
    
    # دستورات جدید مدیریت کانال
    application.add_handler(CommandHandler("setinterval", set_interval_command))
    application.add_handler(CommandHandler("sendnow", send_now_command))
    application.add_handler(CommandHandler("channelstatus", channel_status_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ ربات آماده اجرا است...")
    print(f"📢 سیستم ارسال خودکار قیمت به کانال هر {ADMIN_SETTINGS['channel_interval']} دقیقه فعال است")
    application.run_polling()

if __name__ == "__main__":

    main()
