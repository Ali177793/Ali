import telebot
from telebot import types
import sqlite3
import re
import os

BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_ID = int(os.environ['CHANNEL_ID'])
# نحول النص لأرقام ونحذف الفراغات
ADMIN_IDS = [int(x.strip()) for x in os.environ['ADMIN_IDS'].split(',')]

bot = telebot.TeleBot(BOT_TOKEN)
conn = sqlite3.connect('db.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS products
               (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, name TEXT, price TEXT, photo TEXT)''')
conn.commit()

KEYWORDS = {
    'كيك وحلويات': ['كيك', 'كعك', 'حلويات', 'بقلاوة', 'معمول', 'كاتو', 'دونات'],
    'البان واجبان': ['لبن', 'جبن', 'جبنة', 'حليب', 'زبادي', 'قشطة', 'قيمر', 'اجبان'],
    'مشروبات': ['ببسي', 'كولا', 'عصير', 'مي', 'ماء', 'سفن', 'ميرندا', 'طاقة', 'ريدبول'],
    'معلبات': ['تونة', 'فاصوليا', 'حمص', 'فول', 'معلب', 'صلصة', 'مربى', 'شيبس'],
    'منظفات': ['تايت', 'زاهي', 'قاصر', 'شامبو', 'صابون', 'منظف', 'فيري', 'كلوركس'],
    'بهارات': ['فلفل', 'كمون', 'كركم', 'بهار', 'ملح', 'دارسين', 'بابريكا'],
    'كوزمتك': ['مكياج', 'كريم', 'روج', 'كحل', 'مسكارة', 'فاونديشن', 'بودرة', 'عطر', 'لوشن', 'بلسم', 'مناكير', 'اظافر', 'رموش']
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

@bot.channel_post_handler(content_types=['photo'])
def save(message):
    if message.chat.id!= CHANNEL_ID: return
    text = message.caption or ""
    category = detect_category(text)
    price = get_price(text)
    if not price: 
        for admin in ADMIN_IDS: bot.send_message(admin, '❌ ما لكيت سعر. اكتب رقم')
        return

    photo = message.photo[-1].file_id
    cur.execute("INSERT INTO products (category, name, price, photo) VALUES (?,?,?,?)",
                (category, '', price, photo))
    conn.commit()
    for admin in ADMIN_IDS: 
        bot.send_message(admin, f'✅ تم حفظ منتج جديد\n📦 القسم: {category}\n💰 {price} د.ع')

def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    cur.execute('SELECT DISTINCT category FROM products ORDER BY id DESC')
    cats = [row[0] for row in cur.fetchall()]
    for cat in cats:
        markup.add(types.InlineKeyboardButton(cat, callback_data=f'cat_{cat}'))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    markup = main_menu()
    if not markup.keyboard:
        return bot.send_message(message.chat.id, 'أهلا بيك 👋\nالمنتجات قيد الإضافة')
    bot.send_message(message.chat.id, '*اختر القسم 👇*', reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def buttons(call):
    user_id = call.from_user.id
    is_admin = user_id in ADMIN_IDS

    if call.data == 'back_to_menu':
        bot.delete_message(call.message.chat.id, call.message.message_id)
        markup = main_menu()
        bot.send_message(call.message.chat.id, '*اختر القسم 👇*', reply_markup=markup, parse_mode='Markdown')
        return bot.answer_callback_query(call.id)

    if call.data.startswith('cat_'):
        cat = call.data[4:]
        cur.execute("SELECT id, price, photo FROM products WHERE category=? ORDER BY id DESC", (cat,))
        items = cur.fetchall()
        if not items:
            bot.answer_callback_query(call.id, 'ماكو منتجات')
            return

        bot.answer_callback_query(call.id)
        bot.delete_message(call.message.chat.id, call.message.message_id)

        for pid, price, photo in items:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('🛒 اطلب الان', callback_data=f'order_{pid}'))
            if is_admin:
                markup.add(types.InlineKeyboardButton('🗑️ حذف', callback_data=f'del_{pid}'))
            bot.send_photo(call.message.chat.id, photo, caption=f'💰 *السعر: {price} د.ع*',
                           reply_markup=markup, parse_mode='Markdown')

        back_markup = types.InlineKeyboardMarkup()
        back_markup.add(types.InlineKeyboardButton('⬅️ رجوع للأقسام', callback_data='back_to_menu'))
        bot.send_message(call.message.chat.id, 'اختر منتج او ارجع للأقسام', reply_markup=back_markup)

    elif call.data.startswith('order_'):
        pid = call.data.split('_')[1]
        cur.execute("SELECT price FROM products WHERE id=?", (pid,))
        result = cur.fetchone()
        if not result:
            bot.answer_callback_query(call.id, 'المنتج انحذف')
            return

        price = result[0]
        user = call.from_user
        username = f'@{user.username}' if user.username else user.first_name
        # الطلب يروح لكل المدراء
        for admin in ADMIN_IDS:
            bot.send_message(admin, f'طلب جديد 🔥\n💰 {price} د.ع\n👤 {username}\n🆔 {user.id}')
        bot.answer_callback_query(call.id, 'تم ارسال طلبك! ✅')

    elif call.data.startswith('del_'):
        if not is_admin:
            bot.answer_callback_query(call.id, 'ما عندك صلاحية')
            return

        pid = call.data.split('_')[1]
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        bot.answer_callback_query(call.id, 'تم الحذف')
        bot.delete_message(call.message.chat.id, call.message.message_id)

print("البوت شغال...")
bot.infinity_polling()
