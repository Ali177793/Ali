from telebot import types
import telebot
import sqlite3
import re
import os

BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_ID = int(os.environ['CHANNEL_ID'])
ADMIN_IDS = [int(x.strip()) for x in os.environ['ADMIN_IDS'].split(',')]
SUPPORT_USERNAME = os.environ.get('SUPPORT_USERNAME', '')

bot = telebot.TeleBot(BOT_TOKEN)
conn = sqlite3.connect('db.db', check_same_thread=False)
cur = conn.cursor()
# ضفت حقل description
cur.execute('''CREATE TABLE IF NOT EXISTS products
               (id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                name TEXT,
                description TEXT,
                price TEXT,
                photo TEXT)''')
conn.commit()

KEYWORDS = {
    'كيك وحلويات': ['كيك', 'كعك', 'حلويات', 'بقلاوة', 'معمول', 'كاتو', 'دونات'],
    'البان واجبان': ['لبن', 'جبنة', 'حليب', 'زبادي', 'قشطة', 'قيمر', 'اجبان'],
    'مشروبات': ['ببسي', 'كولا', 'عصير', 'مي', 'ماء', 'سفن', 'ميرندا', 'طاقة', 'ريدبول'],
    'معلبات': ['تونة', 'فاصوليا', 'حمص', 'فول', 'معلب', 'صلصة', 'مربى', 'شيبس'],
    'منظفات': ['تايت', 'زاهي', 'قاصر', 'شامبو', 'صابون', 'منظف', 'فيري', 'كلوركس'],
    'بهارات': ['فلفل', 'كمون', 'كركم', 'بهار', 'ملح', 'دارسين', 'بابريكا'],
    'كوزمتك': ['مكياج', 'كريم', 'روج', 'كحل', 'مسكارة', 'فاونديشن', 'بودرة', 'عطر', 'لوشن', 'بلسم', 'مناكير', 'اظافر', 'رموش'],
    'الجمله': ['جملة', 'جمله', 'كارتون', 'درزن', 'بالجملة', 'جمله']
}

def detect_category(text):
    text = text.lower()
    for category, words in KEYWORDS.items():
        for word in words:
            if word in text:
                return category
    return 'منتجات اخرى'

def get_price(text):
    match = re.search(r'(\d[\d,]*)', text.replace(' ', ''))
    return match.group(1).replace(',', '') if match else None

def extract_name_desc(text):
    # نشيل السعر من النص عشان ما يدخل بالاسم او الوصف
    text_without_price = re.sub(r'\d[\d,]*', '', text).strip()
    lines = [line.strip() for line in text_without_price.split('\n') if line.strip()]

    if not lines:
        return 'بدون اسم', ''

    name = lines[0][:50] # اول سطر هو الاسم
    description = '\n'.join(lines[1:])[:300] # باقي السطور وصف، حد اقصى 300 حرف

    return name or 'بدون اسم', description

def safe_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

@bot.channel_post_handler(content_types=['photo'])
def save(message):
    if message.chat.id!= CHANNEL_ID: return
    text = message.caption or ""
    category = detect_category(text)
    price = get_price(text)
    name, description = extract_name_desc(text)

    if not price:
        for admin in ADMIN_IDS:
            bot.send_message(admin, f'❌ ما لكيت سعر بالمنشور:\n{text[:100]}')
        return

    photo = message.photo[-1].file_id
    cur.execute("INSERT INTO products (category, name, description, price, photo) VALUES (?,?,?,?,?)",
                (category, name, description, price, photo))
    conn.commit()

    notif = f'✅ تم حفظ منتج جديد\n📦 القسم: {category}\n🏷️ {name}\n💰 {price} د.ع'
    if description:
        notif += f'\n📝 {description[:50]}...'

    for admin in ADMIN_IDS:
        bot.send_message(admin, notif)

def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    cur.execute('SELECT DISTINCT category FROM products ORDER BY category')
    cats = [row[0] for row in cur.fetchall()]

    for cat in cats:
        markup.add(types.InlineKeyboardButton(cat, callback_data=f'cat_{cat}'))

    if SUPPORT_USERNAME:
        markup.add(types.InlineKeyboardButton('📞 استفسار او طلب جملة', url=f'https://t.me/{SUPPORT_USERNAME}'))

    return markup

@bot.message_handler(commands=['start'])
def start(message):
    markup = main_menu()
    text = 'أهلا بيك 👋\n*اختر القسم 👇*\n\nعندك سؤال او تريد طلب جملة؟ دوس "استفسار او طلب جملة"'
    if not markup.keyboard:
        return bot.send_message(message.chat.id, 'أهلا بيك 👋\nالمنتجات قيد الإضافة')
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def buttons(call):
    user_id = call.from_user.id
    is_admin = user_id in ADMIN_IDS

    if call.data == 'back_to_menu':
        safe_delete(call.message.chat.id, call.message.message_id)
        markup = main_menu()
        bot.send_message(call.message.chat.id, '*اختر القسم 👇*', reply_markup=markup, parse_mode='Markdown')
        return bot.answer_callback_query(call.id)

    if call.data.startswith('cat_'):
        cat = call.data[4:]
        cur.execute("SELECT id, name, description, price, photo FROM products WHERE category=? ORDER BY id DESC LIMIT 20", (cat,))
        items = cur.fetchall()
        if not items:
            bot.answer_callback_query(call.id, 'ماكو منتجات')
            return

        bot.answer_callback_query(call.id)
        safe_delete(call.message.chat.id, call.message.message_id)

        for pid, name, description, price, photo in items:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('🛒 اطلب الان', callback_data=f'order_{pid}'))
            if is_admin:
                markup.add(types.InlineKeyboardButton('🗑️ حذف', callback_data=f'del_{pid}'))

            # هنا نعرض الوصف
            caption = f'🏷️ *{name}*\n💰 *السعر: {price} د.ع*'
            if description:
                caption += f'\n\n📝 {description}'

            bot.send_photo(call.message.chat.id, photo, caption=caption,
                           reply_markup=markup, parse_mode='Markdown')

        back_markup = types.InlineKeyboardMarkup()
        back_markup.add(types.InlineKeyboardButton('⬅️ رجوع للأقسام', callback_data='back_to_menu'))
        if SUPPORT_USERNAME:
            back_markup.add(types.InlineKeyboardButton('📞 استفسار', url=f'https://t.me/{SUPPORT_USERNAME}'))
        bot.send_message(call.message.chat.id, 'اختر منتج او ارجع للأقسام', reply_markup=back_markup)

    elif call.data.startswith('order_'):
        pid = call.data.split('_')[1]
        cur.execute("SELECT name, price FROM products WHERE id=?", (pid,))
        result = cur.fetchone()
        if not result:
            bot.answer_callback_query(call.id, 'المنتج انحذف')
            return

        name, price = result
        user = call.from_user
        username = f'@{user.username}' if user.username else user.first_name
        for admin in ADMIN_IDS:
            bot.send_message(admin, f'طلب جديد 🔥\n🏷️ {name}\n💰 {price} د.ع\n👤 {username}\n🆔 `{user.id}`', parse_mode='Markdown')
        bot.answer_callback_query(call.id, 'تم ارسال طلبك! ✅')

    elif call.data.startswith('del_'):
        if not is_admin:
            bot.answer_callback_query(call.id, 'ما عندك صلاحية')
            return

        pid = call.data.split('_')[1]
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        bot.answer_callback_query(call.id, 'تم الحذف')
        safe_delete(call.message.chat.id, call.message.message_id)

print("البوت شغال...")
bot.infinity_polling()
