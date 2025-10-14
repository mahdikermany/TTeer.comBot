from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, JobQueue
import requests
import jdatetime
from datetime import datetime, timedelta
import logging
import re
import json
import os

# ================== تنظيمات اوليه ==================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.environ.get('8221687298:AAFFX7UWVspNI8W-KThb_0VtDT_w2dffPIA')
if not TOKEN:
    print("❌ توکن پیدا نشد! لطفا در Render تنظیم کن")
    exit(1)
ADMIN_USER_ID = 72046362
CHANNEL_ID = "-1002317288060"

# ================== توابع کمکي ==================
def get_iran_time():
    iran_time = datetime.now() + timedelta(hours=3, minutes=30)
    jalali_date = jdatetime.datetime.fromgregorian(datetime=iran_time)
    persian_date = jalali_date.strftime("%Y%m%d")
    persian_time = jalali_date.strftime("%H:%M")
    persian_date_display = jalali_date.strftime("%Y/%m/%d")
    persian_time_full = jalali_date.strftime("%H%M%S")
    
    return persian_date, persian_time, persian_date_display, persian_time_full

# ================== مديريت فايل‌ها و ديتابيس ==================
ADMIN_SETTINGS_FILE = "admin_settings.json"

def load_admin_settings():
    default_settings = {
        "order_notifications": True,
        "channel_interval": 30  # مدت زمان بين ارسال پيام‌ها به کانال (دقيقه)
    }
    
    if os.path.exists(ADMIN_SETTINGS_FILE):
        with open(ADMIN_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            saved_settings = json.load(f)
            # اضافه کردن کليدهاي جديد اگر وجود ندارند
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

# ================== تنظيمات شبکه‌ها و کيف پول‌ها ==================
NETWORK_FEES = {
    "ERC20": 7,
    "TRC20": 5, 
    "BEP20": 2,
    "Solana": 2
}

NETWORK_DISPLAY_NAMES = {
    "ERC20": "ERC20 (اتريوم)",
    "TRC20": "TRC20 (ترون)", 
    "BEP20": "BEP20 (بايننس)",
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

# ================== سيستم ارسال خودکار به کانال ==================
async def send_channel_price(context: ContextTypes.DEFAULT_TYPE):
    try:
        tether_price, gold_price, gold_ounce, gold_dollar_price = await get_accurate_prices()
        persian_date, persian_time, persian_date_display, _ = get_iran_time()
        
        tether_display = f"{tether_price:,}" if tether_price > 0 else "0"
        gold_display = f"{gold_price:,}" if gold_price > 0 else "0"
        gold_ounce_display = f"{gold_ounce:,}" if gold_ounce > 0 else "0"
        gold_dollar_display = f"{gold_dollar_price:,}" if gold_dollar_price > 0 else "0"
        
        message = f"""?? *قيمت لحظه‌اي تتر و طلا*

 ?? *نرخ تتر*                   `{tether_display}` تومان
?? *طلا 18 عيار*     `{gold_display}` تومان 
 ?? *انس جهاني*                `{gold_ounce_display}` دلار
 ?? *قيمت دلار طلا*       `{gold_dollar_display}` تومان

ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ
?? {persian_date_display}
? {persian_time}

?? [قيمت الان چند؟](https://t.me/TTeer_com_bot)"""
        
        await context.bot.send_message(
            chat_id=CHANNEL_ID, 
            text=message, 
            parse_mode='Markdown'
        )
        logging.info(f"? قيمت به کانال {CHANNEL_ID} ارسال شد - فاصله: {ADMIN_SETTINGS['channel_interval']} دقيقه")
    except Exception as e:
        logging.error(f"? خطا در ارسال قيمت به کانال: {e}")

# ================== سيستم تأييد هويت ==================
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
        "?? *براي تاييد هويت*\n\n"
        "لطفاً کد اشتراک خود را وارد کنيد:\n\n"
        "درصورت نداشتن کد اشتراک به پشتيباني پيام دهيد:\n"
        "?? پشتيباني: @TTeercom",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("?? قيمت الان چند؟")]], resize_keyboard=True)
    )

async def verify_subscription_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code):
    user_id = update.message.from_user.id
    
    if code == "?? قيمت الان چند؟":
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
        await update.message.reply_text("? کد اشتراک تأييد شد!\n\nلطفاً کد ملي خود را وارد کنيد:")
    else:
        await update.message.reply_text(
            "? کد اشتراک نامعتبر!\n\nلطفاً کد صحيح را وارد کنيد يا براي بازگشت روي '?? قيمت الان چند؟' کليک کنيد.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("?? قيمت الان چند؟")]], resize_keyboard=True)
        )

async def verify_national_code(update: Update, context: ContextTypes.DEFAULT_TYPE, national_code):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    
    if national_code == "?? قيمت الان چند؟":
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
            
            await update.message.reply_text(f"? تأييد هويت کامل شد!\n\nسلام {user_name} عزيز!", reply_markup=main_menu_keyboard())
            
            if service_type == "buy":
                await show_buy_options(update, context)
            elif service_type == "sell":
                await show_sell_options(update, context)
        else:
            await update.message.reply_text(
                "? کد ملي با اطلاعات ثبت شده مطابقت ندارد!\n\nلطفاً کد ملي صحيح را وارد کنيد.",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("?? قيمت الان چند؟")]], resize_keyboard=True)
            )
    else:
        await update.message.reply_text(
            "? کد ملي نامعتبر! بايد 10 رقم باشد.\n\nلطفاً کد ملي صحيح را وارد کنيد.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("?? قيمت الان چند؟")]], resize_keyboard=True)
        )

# ================== سيستم خريد ==================
async def show_buy_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    tether_price, _, _, _ = await get_accurate_prices()
    
    USER_STATES[user_id] = {
        "waiting_for_buy_amount": True,
        "service_type": "buy",
        "current_price": tether_price
    }
    
    await update.message.reply_text(
        f"?? *خريد تتر از ما*\n\n?? قيمت فعلي خريد تتر: {tether_price:,} تومان\n\n"
        "لطفاً مبلغ مورد نظر را به تومان وارد کنيد:\n\nمثال: 1000000\n\n"
        "يا از دکمه‌هاي زير انتخاب کنيد:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("5,000,000 تومان"), KeyboardButton("10,000,000 تومان")],
            [KeyboardButton("15,000,000 تومان"), KeyboardButton("20,000,000 تومان")],
            [KeyboardButton("?? قيمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, amount_text):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    current_price = user_state["current_price"]
    
    if amount_text == "?? قيمت الان چند؟":
        await price_command(update, context)
        return
    
    try:
        clean_amount = re.sub(r'[^\d]', '', amount_text)
        amount = int(clean_amount)
        
        if amount < 1000000:
            await update.message.reply_text(
                "? مبلغ بسيار کم!\n\nحداقل مبلغ خريد 1,000,000 تومان است.\n\nلطفاً مبلغ معتبر وارد کنيد:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("5,000,000 تومان"), KeyboardButton("10,000,000 تومان")],
                    [KeyboardButton("15,000,000 تومان"), KeyboardButton("20,000,000 تومان")],
                    [KeyboardButton("?? قيمت الان چند؟")]
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
            f"? *خلاصه سفارش خريد*\n\n?? مبلغ: {amount:,} تومان\n"
            f"?? تعداد تتر محاسبه شده: {tether_amount:.2f}\n"
            f"?? قيمت هر تتر: {current_price:,} تومان\n\n"
            "آيا از سفارش خود اطمينان داريد?",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("? تأييد و ادامه"), KeyboardButton("? انصراف")],
                [KeyboardButton("?? قيمت الان چند؟")]
            ], resize_keyboard=True)
        )
        
    except ValueError:
        await update.message.reply_text(
            "? مبلغ نامعتبر!\n\nلطفاً مبلغ را به صورت عددي وارد کنيد:\n\nمثال: 1000000",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("5,000,000 تومان"), KeyboardButton("10,000,000 تومان")],
                [KeyboardButton("15,000,000 تومان"), KeyboardButton("20,000,000 تومان")],
                [KeyboardButton("?? قيمت الان چند؟")]
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
        f"?? **شبکه انتخاب شده: {NETWORK_DISPLAY_NAMES[network]}**\n\n"
        f"?? کارمزد شبکه: {network_fee} تتر\n"
        f"?? تتر محاسبه شده: {tether_amount:.2f}\n"
        f"?? *تتر دريافتي شما*: {final_tether_amount:.2f} تتر\n\n"
        "*لطفاً آدرس کيف پول خود را ارسال کنيد*:",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("? انصراف")]], resize_keyboard=True)
    )

async def handle_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE, wallet_address):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if wallet_address == "? انصراف":
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
        f"?? *سفارش خريد شما ثبت شد* \n\n"
        f"??  مبلغ واريز شما: `{user_state['amount']:,}` تومان\n"
        f"?? تعداد تتر دريافتي شما: `{user_state['final_tether_amount']:.2f}` تتر\n"
        f"?? قيمت خريد: `{user_state['current_price']:,}` تومان\n"
        f"?? شبکه انتخابي شما: {NETWORK_DISPLAY_NAMES[user_state['selected_network']]}\n"
        f"?? آدرس کيف پول شما:\n`{wallet_address}`\n\n"
        f"?? کد پيگيري:\n`{tracking_code}`\n\n"
        f"?? {persian_date_display} - {persian_time}\n\n"
        "?? **لطفاً اين پيام را براي پشتيباني ارسال کنيد:**\n@TTeercom\n\n"
        "? **توجه:** اين سفارش تنها به مدت 10 دقيقه معتبر است و پس از آن قيمت ممکن است تغيير کند."
    )
    
    await update.message.reply_text(final_message, parse_mode='Markdown', reply_markup=main_menu_keyboard())
    
    if ADMIN_SETTINGS["order_notifications"]:
        try:
            admin_message = (
                f"?? *سفارش خريد #{order_number}* \n\n"
                f"?? کاربر: {update.message.from_user.first_name}\n"
                f"?? کاربري: `{user_id}`\n"
                f"?? تماس با کاربر: [کليک کنيد](tg://user?id={user_id})\n\n"
                f"?? مبلغ دريافتي ما: {user_state['amount']:,} تومان\n"
                f"?? تتر پرداختي ما: {user_state['final_tether_amount']:.2f}\n"
                f"?? قيمت: {user_state['current_price']:,} تومان\n"
                f"?? شبکه: {user_state['selected_network']}\n"
                f"?? آدرس کيف پول مشتري:\n`{wallet_address}`\n\n"
                f"?? کد پيگيري: `{tracking_code}`"
            )
            
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"خطا در ارسال به ادمين: {e}")
    
    del USER_STATES[user_id]

# ================== سيستم فروش (با اطلاعات بانکي جديد) ==================
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
        f"?? *فروش تتر به ما* \n\n?? قيمت فعلي خريد تتر: {tether_price:,} تومان\n"
        f"?? *قيمت فعلي فروش تتر* : *{sell_price:,}* *تومان* \n\n"
        "لطفاً تعداد تتر مورد نظر را وارد کنيد:\n\nمثال: 10\n\n"
        "يا از دکمه‌هاي زير انتخاب کنيد:",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("10 تتر"), KeyboardButton("20 تتر")],
            [KeyboardButton("50 تتر"), KeyboardButton("100 تتر")],
            [KeyboardButton("?? قيمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_sell_amount(update: Update, context: ContextTypes.DEFAULT_TYPE, amount_text):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    sell_price = user_state["sell_price"]
    
    if amount_text == "?? قيمت الان چند؟":
        await price_command(update, context)
        return
    
    try:
        clean_amount = re.sub(r'[^\d]', '', amount_text)
        tether_amount = float(clean_amount)
        
        if tether_amount < 1:
            await update.message.reply_text(
                "? تعداد بسيار کم!\n\nحداقل تعداد فروش 1 تتر است.\n\nلطفاً تعداد معتبر وارد کنيد:",
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("10 تتر"), KeyboardButton("20 تتر")],
                    [KeyboardButton("50 تتر"), KeyboardButton("100 تتر")],
                    [KeyboardButton("?? قيمت الان چند؟")]
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
            f"? *خلاصه سفارش فروش* \n\n?? *تعداد تتر فروشي شما:*  {tether_amount}\n"
            f"?? مبلغ دريافتي شما: *{amount:,}* تومان\n\n"
            "آيا از سفارش خود اطمينان داريد?",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("? تأييد و ادامه"), KeyboardButton("? انصراف")],
                [KeyboardButton("?? قيمت الان چند؟")]
            ], resize_keyboard=True)
        )
        
    except ValueError:
        await update.message.reply_text(
            "? تعداد نامعتبر!\n\nلطفاً تعداد تتر را به صورت عددي وارد کنيد:\n\nمثال: 10",
            reply_markup=ReplyKeyboardMarkup([
                [KeyboardButton("10 تتر"), KeyboardButton("20 تتر")],
                [KeyboardButton("50 تتر"), KeyboardButton("100 تتر")],
                [KeyboardButton("?? قيمت الان چند؟")]
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
        "?? *لطفا شماره کارت خود را جهت واريز وجه وارد کنيد* \n\n"
        "????  در صورت اينکه شماره کارت به نام غير باشد وجه واريز نخواهد شد",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("لازم نيست")],
            [KeyboardButton("?? قيمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_card_number(update: Update, context: ContextTypes.DEFAULT_TYPE, card_number):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if card_number == "?? قيمت الان چند؟":
        await price_command(update, context)
        return
    
    if card_number == "لازم نيست":
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
        "?? *لطفاً شماره حساب خود را وارد کنيد* ",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("لازم نيست")],
            [KeyboardButton("?? قيمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_account_number(update: Update, context: ContextTypes.DEFAULT_TYPE, account_number):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if account_number == "?? قيمت الان چند؟":
        await price_command(update, context)
        return
    
    if account_number == "لازم نيست":
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
        "?? **لطفاً شماره شبا خود را وارد کنيد**\n\n"
        "???? نيازي به وارد کردن IR نيست، فقط اعداد را وارد کنيد",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("لازم نيست")],
            [KeyboardButton("?? قيمت الان چند؟")]
        ], resize_keyboard=True)
    )

async def handle_sheba_number(update: Update, context: ContextTypes.DEFAULT_TYPE, sheba_number):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if sheba_number == "?? قيمت الان چند؟":
        await price_command(update, context)
        return
    
    if sheba_number == "لازم نيست":
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
        "?? *لطفاً نام دارنده حساب را وارد کنيد* \n\n"
        "??هشدار مهم??\n  حساب بايد به نام خودتان باشد، در غير اين صورت وجه واريز نخواهد شد",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("? انصراف")]], resize_keyboard=True)
    )

async def handle_account_holder(update: Update, context: ContextTypes.DEFAULT_TYPE, account_holder):
    user_id = update.message.from_user.id
    user_state = USER_STATES[user_id]
    
    if account_holder == "? انصراف":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await price_command(update, context)
        return
    
    wallet_address = WALLET_ADDRESSES.get(user_state["selected_network"], "")
    
    if not wallet_address:
        await update.message.reply_text(
            "? آدرس کيف پول براي اين شبکه تنظيم نشده است.\n\nلطفاً با پشتيباني تماس بگيريد.",
            reply_markup=main_menu_keyboard()
        )
        del USER_STATES[user_id]
        return
    
    persian_date, persian_time, persian_date_display, persian_time_full = get_iran_time()
    tracking_code = f"{persian_date}{persian_time_full}-{user_id}"
    
    ORDER_COUNTERS["sell"] += 1
    save_order_counters()
    order_number = ORDER_COUNTERS["sell"]
    
    # ساخت بخش اطلاعات بانکي به صورت شرطي
    bank_info = "?? **اطلاعات بانکي شما:**\n"
    if user_state['card_number']:
        bank_info += f"• شماره کارت:\n`{user_state['card_number']}`\n\n"
    if user_state['account_number']:
        bank_info += f"• شماره حساب:\n`{user_state['account_number']}`\n\n"
    if user_state['sheba_display']:
        bank_info += f"• شماره شبا:\n`{user_state['sheba_display']}`\n\n"
    bank_info += f"• نام دارنده حساب:\n`{account_holder}`\n\n"
    
    final_message = (
        f"?? *سفارش فروش شما ثبت شد* \n\n"
        f"?? تعداد تتري که بايد واريز کنيد: `{user_state['tether_amount']}`\n"
        f"?? شبکه: {NETWORK_DISPLAY_NAMES[user_state['selected_network']]}\n\n"
        f"?? آدرس کيف پول براي واريز:\n`{wallet_address}`\n\n"
        "?? **بعد از واريزي، فيش واريزي تتر را براي پشتيبان ارسال نماييد:**\n@TTeercom\n"
        f"ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ\n\n"
        f"?? *مبلغ دريافتي شما* : `{user_state['amount']:,}` تومان\n"
        f"?? قيمت فروش: `{user_state['sell_price']:,}` تومان\n\n"
        f"{bank_info}"
        f"?? کد پيگيري:\n`{tracking_code}`\n"
        f"?? {persian_date_display} - {persian_time}\n\n"
        "? **توجه مهم:** اين فرآيند بايد حداکثر تا 10 دقيقه از زمان ثبت انجام شود."
    )
    
    await update.message.reply_text(final_message, parse_mode='Markdown', reply_markup=main_menu_keyboard())
    
    if ADMIN_SETTINGS["order_notifications"]:
        try:
            # ساخت بخش اطلاعات بانکي براي ادمين
            admin_bank_info = "?? **اطلاعات بانکي:**\n"
            if user_state['card_number']:
                admin_bank_info += f"• شماره کارت: `{user_state['card_number']}`\n"
            if user_state['account_number']:
                admin_bank_info += f"• شماره حساب: `{user_state['account_number']}`\n"
            if user_state['sheba_display']:
                admin_bank_info += f"• شماره شبا: `{user_state['sheba_display']}`\n"
            admin_bank_info += f"• نام دارنده حساب: `{account_holder}`\n\n"
            
            admin_message = (
                f"?? **سفارش فروش #{order_number}**\n\n"
                f"?? کاربر: {update.message.from_user.first_name}\n"
                f"?? کاربري: `{user_id}`\n"
                f"?? تماس با کاربر: [کليک کنيد](tg://user?id={user_id})\n\n"
                f"?? تتر دريافتي: {user_state['tether_amount']}\n"
                f"?? *مبلغي پرداختي ما:* `{user_state['amount']:,}` *تومان*\n"
                f"?? قيمت فروش: {user_state['sell_price']:,} تومان\n"
                f"?? شبکه: {user_state['selected_network']}\n\n"
                f"{admin_bank_info}"
                f"?? کد پيگيري: `{tracking_code}`"
            )
            
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message, parse_mode='Markdown')
        except Exception as e:
            logging.error(f"خطا در ارسال به ادمين: {e}")
    
    del USER_STATES[user_id]

# ================== سيستم دريافت قيمت‌ها ==================
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
        logging.error(f"? خطا در دريافت قيمت تتر: {e}")

    gold_price = 0
    try:
        response = requests.get('https://milli.gold/api/v1/public/milli-price/external', headers=headers, timeout=10)
        data = response.json()
        if 'price18' in data:
            gold_price = int(data['price18']) * 100
    except Exception as e:
        logging.error(f"? خطا در دريافت قيمت طلا: {e}")

    gold_ounce = 0
    try:
        response = requests.get('https://data-asg.goldprice.org/dbXRates/USD', headers=headers, timeout=10)
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            gold_ounce = int(float(data['items'][0]['xauPrice']))
    except Exception as e:
        logging.error(f"? خطا در دريافت انس جهاني: {e}")

    gold_dollar_price = 0
    if gold_price > 0 and gold_ounce > 0:
        try:
            gold_dollar_price = int((gold_price * 31.1035) / (gold_ounce * 0.75))
        except:
            gold_dollar_price = 0

    return tether_price, gold_price, gold_ounce, gold_dollar_price

# ================== دستورات کاربري ==================
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in USER_STATES:
        del USER_STATES[user_id]
    
    wait_msg = await update.message.reply_text("?? در حال دريافت آخرين قيمت‌ها...")
    tether_price, gold_price, gold_ounce, gold_dollar_price = await get_accurate_prices()
    persian_date, persian_time, persian_date_display, _ = get_iran_time()
    
    tether_display = f"{tether_price:,}" if tether_price > 0 else "0"
    gold_display = f"{gold_price:,}" if gold_price > 0 else "0"
    gold_ounce_display = f"{gold_ounce:,}" if gold_ounce > 0 else "0"
    gold_dollar_display = f"{gold_dollar_price:,}" if gold_dollar_price > 0 else "0"
    
    message = f"""?? *قيمت الان...*

 ?? *نرخ تتر*                   `{tether_display}` تومان
?? *طلا 18 عيار*     `{gold_display}` تومان 
 ?? *انس جهاني*                `{gold_ounce_display}` دلار
 ?? *قيمت دلار طلا*       `{gold_dollar_display}` تومان

ــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــــ
??{persian_date_display}
?{persian_time}

?? [قيمت الان چند؟](https://t.me/TTeer_com_bot)"""
    
    await wait_msg.delete()
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=main_menu_keyboard())

def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("?? قيمت لحظه اي تتر و طلا")],
        [KeyboardButton("?? خريد تتر از ما"), KeyboardButton("?? فروش تتر به ما")],
        [KeyboardButton("?? راهنما"), KeyboardButton("?? کانال ما")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    save_user(user_id, user_name)
    
    welcome_message = f"""?? سلام {user_name}!
به ربات تتردات کام خوش آمديد!

?? **امکانات ربات:**
• دريافت قيمت لحظه‌اي تتر و طلا
• خريد و فروش امن تتر
• پشتيباني 24 ساعته

?? **کانال اطلاع‌رساني ما:**
@TTeer_com

لطفاً يکي از گزينه‌هاي زير را انتخاب کنيد:"""
    
    await update.message.reply_text(welcome_message, reply_markup=main_menu_keyboard())

# ================== دستورات مديريت کانال ==================
async def set_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "?? **دستور تنظيم فاصله ارسال به کانال:**\n\nUsage: /setinterval <دقيقه>\n\nمثال:\n/setinterval 30\n/setinterval 15"
        )
        return
    
    try:
        interval = int(context.args[0])
        if interval < 5:
            await update.message.reply_text("? فاصله ارسال نمي‌تواند کمتر از 5 دقيقه باشد!")
            return
        
        ADMIN_SETTINGS["channel_interval"] = interval
        save_admin_settings(ADMIN_SETTINGS)
        
        # توقف و راه‌اندازي مجدد job با فاصله جديد
        job_queue = context.application.job_queue
        if job_queue:
            # حذف jobهاي قبلي
            for job in job_queue.jobs():
                if job.name == "channel_price_job":
                    job.schedule_removal()
            
            # ايجاد job جديد با فاصله جديد
            job_queue.run_repeating(
                send_channel_price,
                interval=interval * 60,  # تبديل به ثانيه
                first=10,  # 10 ثانيه بعد
                name="channel_price_job"
            )
        
        await update.message.reply_text(f"? فاصله ارسال به کانال به {interval} دقيقه تنظيم شد!")
        
    except ValueError:
        await update.message.reply_text("? مقدار نامعتبر! لطفاً يک عدد وارد کنيد.")

async def send_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    try:
        await send_channel_price(context)
        await update.message.reply_text("? قيمت با موفقيت به کانال ارسال شد!")
    except Exception as e:
        await update.message.reply_text(f"? خطا در ارسال به کانال: {e}")

async def channel_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    try:
        # بررسي وضعيت کانال
        channel_info = await context.bot.get_chat(CHANNEL_ID)
        channel_members = await context.bot.get_chat_members_count(CHANNEL_ID)
        
        status_message = f"""
?? **وضعيت کانال:**

?? نام کانال: {channel_info.title}
?? تعداد اعضا: {channel_members}
? فاصله ارسال: {ADMIN_SETTINGS['channel_interval']} دقيقه
?? وضعيت ارسال خودکار: ? فعال

?? **دستورات مديريت کانال:**
• /setinterval <دقيقه> - تنظيم فاصله ارسال
• /sendnow - ارسال فوري قيمت
• /channelstatus - نمايش اين وضعيت
"""
        await update.message.reply_text(status_message)
    except Exception as e:
        await update.message.reply_text(f"? خطا در دريافت وضعيت کانال: {e}")

# ================== دستورات مديريتي ==================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id == ADMIN_USER_ID:
        await admin_help_command(update, context)
        return
    
    help_text = """
?? **راهنماي ربات تتردات کام:**

?? **خريد تتر:**
1. انتخاب گزينه "خريد تتر از ما"
2. وارد کردن کد اشتراک و کد ملي
3. انتخاب مبلغ مورد نظر
4. انتخاب شبکه و وارد کردن آدرس کيف پول

?? **فروش تتر:**
1. انتخاب گزينه "فروش تتر به ما" 
2. وارد کردن کد اشتراک و کد ملي
3. وارد کردن تعداد تتر
4. انتخاب شبکه براي واريز

?? **ساير امکانات:**
• دريافت قيمت لحظه‌اي تتر و طلا
• پشتيباني 24 ساعته

?? پشتيباني:\n @TTeercom
?? کانال:\n @TTeer_com
"""
    await update.message.reply_text(help_text, reply_markup=main_menu_keyboard())

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    notifications_status = "? روشن" if ADMIN_SETTINGS["order_notifications"] else "? خاموش"
    interval_status = f"{ADMIN_SETTINGS['channel_interval']} دقيقه"
    
    help_text = f"""
??? **دستورات مديريتي ربات**

?? **آمار و مديريت:**
• /stats - نمايش آمار کاربران
• /broadcast <پيام> - ارسال پيام به همه کاربران
• /togglenotifications - تغيير وضعيت اطلاع‌رساني ({notifications_status})

?? **مديريت کانال:**
• /setinterval <دقيقه> - تنظيم فاصله ارسال به کانال ({interval_status})
• /sendnow - ارسال فوري قيمت به کانال
• /channelstatus - نمايش وضعيت کانال

?? **مديريت کيف پول:**
• /setwallet <شبکه> <آدرس> - تنظيم آدرس کيف پول
• /wallets - نمايش آدرس‌هاي فعلي

?? **مديريت کدهاي اشتراک:**
• /addcode <کد> <کد_ملي> - اضافه کردن کد اشتراک
• /removecode <کد> - حذف کد اشتراک
• /listcodes - نمايش همه کدها
• /togglecode <کد> - فعال/غيرفعال کردن کد

?? **ساير دستورات:**
• /admin - نمايش اين راهنما
• /help - نمايش راهنماي کاربري

?? **مثال‌ها:**
• /setwallet TRC20 TUvQ6SdWNkj8q7auUegsj7hXADeMhtgExX
• /broadcast اطلاعيه جديد
• /addcode 123456 1234567890
• /setinterval 15
• /sendnow
"""
    await update.message.reply_text(help_text)

async def toggle_notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    ADMIN_SETTINGS["order_notifications"] = not ADMIN_SETTINGS["order_notifications"]
    save_admin_settings(ADMIN_SETTINGS)
    
    status = "? روشن" if ADMIN_SETTINGS["order_notifications"] else "? خاموش"
    await update.message.reply_text(f"? وضعيت اطلاع‌رساني سفارشات به {status} تغيير کرد.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    total_users = USER_STATS["total_users"]
    active_users = len([user for user in USERS_DB if USERS_DB[user]["verified"]])
    
    stats_text = f"""
?? **آمار ربات**

?? تعداد کل کاربران: {total_users}
? کاربران فعال: {active_users}
?? کاربران در حال تراکنش: {len(USER_STATES)}
? فاصله ارسال به کانال: {ADMIN_SETTINGS['channel_interval']} دقيقه

?? **آخرين کاربران:**
"""
    
    user_count = 0
    for user_id, user_data in list(USER_STATS["users"].items())[-5:]:
        user_count += 1
        stats_text += f"\n{user_count}. {user_data['name']} - {user_data['join_date']}"
    
    await update.message.reply_text(stats_text)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not context.args:
        await update.message.reply_text("?? **دستور ارسال پيام همگاني:**\n\nUsage: /broadcast <پيام>\n\nمثال:\n/broadcast اطلاعيه مهم")
        return
    
    message = ' '.join(context.args)
    users_count = 0
    failed_count = 0
    
    for user_id in USER_STATS["users"]:
        try:
            await context.bot.send_message(chat_id=user_id, text=f"?? **پيام همگاني:**\n\n{message}")
            users_count += 1
        except:
            failed_count += 1
    
    await update.message.reply_text(f"? ارسال پيام همگاني انجام شد:\n\n? موفق: {users_count} کاربر\n? ناموفق: {failed_count} کاربر")

async def set_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "?? **دستور تنظيم آدرس کيف پول:**\n\nUsage: /setwallet <network> <address>\n\n"
            "?? شبکه‌هاي موجود:\n- ERC20\n- TRC20\n- BEP20\n- Solana\n\n"
            "مثال:\n/setwallet TRC20 TUvQ6SdWNkj8q7auUegsj7hXADeMhtgExX"
        )
        return
    
    network = context.args[0].upper()
    address = ' '.join(context.args[1:])
    
    if network not in NETWORK_FEES:
        await update.message.reply_text("? شبکه نامعتبر!\n\nشبکه‌هاي معتبر:\n- ERC20\n- TRC20\n- BEP20\n- Solana")
        return
    
    WALLET_ADDRESSES[network] = address
    save_wallet_addresses(WALLET_ADDRESSES)
    
    await update.message.reply_text(
        f"? آدرس کيف پول براي شبکه {NETWORK_DISPLAY_NAMES[network]} با موفقيت تنظيم شد!\n\nآدرس جديد:\n`{address}`",
        parse_mode='Markdown'
    )

async def show_wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    message = "?? **آدرس‌هاي کيف پول فعلي:**\n\n"
    for network, address in WALLET_ADDRESSES.items():
        display_name = NETWORK_DISPLAY_NAMES.get(network, network)
        message += f"?? {display_name}:\n`{address}`\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def add_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "?? **دستور اضافه کردن کد اشتراک:**\n\nUsage: /addcode <کد> <کد_ملي>\n\nمثال:\n/addcode 123456 1234567890"
        )
        return
    
    code = context.args[0]
    national_code = context.args[1]
    
    if code in SUBSCRIBE_CODES:
        await update.message.reply_text(f"? کد اشتراک '{code}' از قبل وجود دارد!")
        return
    
    SUBSCRIBE_CODES[code] = {"national_code": national_code, "active": True}
    save_subscribe_codes()
    
    await update.message.reply_text(f"? کد اشتراک '{code}' با موفقيت اضافه شد!\n\nکد ملي مرتبط: {national_code}")

async def remove_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not context.args:
        await update.message.reply_text("?? **دستور حذف کد اشتراک:**\n\nUsage: /removecode <کد>\n\nمثال:\n/removecode 123456")
        return
    
    code = context.args[0]
    if code not in SUBSCRIBE_CODES:
        await update.message.reply_text(f"? کد اشتراک '{code}' وجود ندارد!")
        return
    
    del SUBSCRIBE_CODES[code]
    save_subscribe_codes()
    await update.message.reply_text(f"? کد اشتراک '{code}' با موفقيت حذف شد!")

async def list_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not SUBSCRIBE_CODES:
        await update.message.reply_text("? هيچ کد اشتراکي وجود ندارد!")
        return
    
    message = "?? **ليست کدهاي اشتراک:**\n\n"
    for code, data in SUBSCRIBE_CODES.items():
        status = "? فعال" if data["active"] else "? غيرفعال"
        message += f"?? کد: `{code}`\n   کد ملي: `{data['national_code']}`\n   وضعيت: {status}\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

async def toggle_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("? دسترسي denied!")
        return
    
    if not context.args:
        await update.message.reply_text("?? **دستور فعال/غيرفعال کردن کد اشتراک:**\n\nUsage: /togglecode <کد>\n\nمثال:\n/togglecode 123456")
        return
    
    code = context.args[0]
    if code not in SUBSCRIBE_CODES:
        await update.message.reply_text(f"? کد اشتراک '{code}' وجود ندارد!")
        return
    
    SUBSCRIBE_CODES[code]["active"] = not SUBSCRIBE_CODES[code]["active"]
    save_subscribe_codes()
    status = "فعال" if SUBSCRIBE_CODES[code]["active"] else "غيرفعال"
    await update.message.reply_text(f"? کد اشتراک '{code}' با موفقيت {status} شد!")

# ================== هندلر اصلي پيام‌ها ==================
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
            if text == "? تأييد و ادامه":
                await update.message.reply_text(
                    "?? **لطفاً شبکه مورد نظر را انتخاب کنيد:**\n\n?? **کارمزد شبکه‌ها:**\n"
                    "• ERC20 (اتريوم) - 7 تتر\n• TRC20 (ترون) - 5 تتر\n"
                    "• BEP20 (بايننس) - 2 تتر\n• Solana (سولانا) - 2 تتر",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("ERC20 (اتريوم)"), KeyboardButton("TRC20 (ترون)")],
                        [KeyboardButton("BEP20 (بايننس)"), KeyboardButton("Solana (سولانا)")],
                        [KeyboardButton("?? قيمت الان چند؟")]
                    ], resize_keyboard=True)
                )
                return
            elif text in ["ERC20 (اتريوم)", "TRC20 (ترون)", "BEP20 (بايننس)", "Solana (سولانا)"]:
                network_map = {
                    "ERC20 (اتريوم)": "ERC20", "TRC20 (ترون)": "TRC20", 
                    "BEP20 (بايننس)": "BEP20", "Solana (سولانا)": "Solana"
                }
                network = network_map[text]
                await handle_network_selection(update, context, network)
                return
            elif text in ["? انصراف", "?? قيمت الان چند؟"]:
                del USER_STATES[user_id]
                await price_command(update, context)
                return
        
        elif state.get("waiting_for_wallet"):
            if text == "? انصراف":
                if user_id in USER_STATES:
                    del USER_STATES[user_id]
                await price_command(update, context)
                return
            else:
                await handle_wallet_address(update, context, text)
                return
        
        elif state.get("waiting_for_sell_network"):
            if text == "? تأييد و ادامه":
                await update.message.reply_text(
                    "?? لطفاً شبکه مورد نظر براي واريز تتر را انتخاب کنيد:",
                    reply_markup=ReplyKeyboardMarkup([
                        [KeyboardButton("ERC20 (اتريوم)"), KeyboardButton("TRC20 (ترون)")],
                        [KeyboardButton("BEP20 (بايننس)"), KeyboardButton("Solana (سولانا)")],
                        [KeyboardButton("?? قيمت الان چند؟")]
                    ], resize_keyboard=True)
                )
                return
            elif text in ["ERC20 (اتريوم)", "TRC20 (ترون)", "BEP20 (بايننس)", "Solana (سولانا)"]:
                network_map = {
                    "ERC20 (اتريوم)": "ERC20", "TRC20 (ترون)": "TRC20", 
                    "BEP20 (بايننس)": "BEP20", "Solana (سولانا)": "Solana"
                }
                network = network_map[text]
                await handle_sell_network_selection(update, context, network)
                return
            elif text in ["? انصراف", "?? قيمت الان چند؟"]:
                del USER_STATES[user_id]
                await price_command(update, context)
                return
        
        # حالت جديد: انتظار براي شماره کارت
        elif state.get("waiting_for_card_number"):
            if text == "?? قيمت الان چند؟":
                await price_command(update, context)
                return
            else:
                await handle_card_number(update, context, text)
                return
        
        # حالت جديد: انتظار براي شماره حساب
        elif state.get("waiting_for_account_number"):
            if text == "?? قيمت الان چند؟":
                await price_command(update, context)
                return
            else:
                await handle_account_number(update, context, text)
                return
        
        # حالت جديد: انتظار براي شماره شبا
        elif state.get("waiting_for_sheba_number"):
            if text == "?? قيمت الان چند؟":
                await price_command(update, context)
                return
            else:
                await handle_sheba_number(update, context, text)
                return
        
        # حالت جديد: انتظار براي نام دارنده حساب
        elif state.get("waiting_for_account_holder"):
            if text == "? انصراف":
                if user_id in USER_STATES:
                    del USER_STATES[user_id]
                await price_command(update, context)
                return
            else:
                await handle_account_holder(update, context, text)
                return
    
    if text == "?? قيمت لحظه اي تتر و طلا":
        await price_command(update, context)
    elif text == "?? خريد تتر از ما":
        await request_subscription_code(update, context, "buy")
    elif text == "?? فروش تتر به ما":
        await request_subscription_code(update, context, "sell")
    elif text == "?? کانال ما":
        await update.message.reply_text(
            "?? **کانال اطلاع‌رساني ما:**\n\n?? @TTeer_com\n\n? قيمت‌هاي لحظه‌اي\n? اخبار و اطلاعيه‌ها",
            reply_markup=main_menu_keyboard()
        )
    elif text == "?? راهنما":
        await help_command(update, context)
    elif text == "?? قيمت الان چند؟":
        await price_command(update, context)
    else:
        await update.message.reply_text("? دستور نامعتبر\nلطفاً از دکمه‌هاي زير استفاده کنيد:", reply_markup=main_menu_keyboard())

# ================== اجراي ربات ==================
def main():
    print("?? ربات تتردات کام با سيستم خريد و فروش پيشرفته فعال شد...")
    application = Application.builder().token(TOKEN).build()
    
    # تنظيم JobQueue براي ارسال خودکار به کانال
    job_queue = application.job_queue
    if job_queue:
        # اطمينان از وجود کليد channel_interval
        if "channel_interval" not in ADMIN_SETTINGS:
            ADMIN_SETTINGS["channel_interval"] = 30
            save_admin_settings(ADMIN_SETTINGS)
            
        interval_seconds = ADMIN_SETTINGS["channel_interval"] * 60
        job_queue.run_repeating(
            send_channel_price,
            interval=interval_seconds,
            first=10,  # 10 ثانيه بعد از راه‌اندازي
            name="channel_price_job"
        )
        print(f"? سيستم ارسال خودکار به کانال فعال شد - فاصله: {ADMIN_SETTINGS['channel_interval']} دقيقه")
    
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
    
    # دستورات جديد مديريت کانال
    application.add_handler(CommandHandler("setinterval", set_interval_command))
    application.add_handler(CommandHandler("sendnow", send_now_command))
    application.add_handler(CommandHandler("channelstatus", channel_status_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("? ربات آماده اجرا است...")
    print(f"?? سيستم ارسال خودکار قيمت به کانال هر {ADMIN_SETTINGS['channel_interval']} دقيقه فعال است")
    application.run_polling()

if __name__ == "__main__":
    main()



