import telebot
from telebot import types
import sqlite3
import re
import os

# 1. ياخذ المتغيرات من Railway - لا تغير شي هنا
BOT_TOKEN = os.environ['BOT_TOKEN']
CHANNEL_ID = int(os.environ['CHANNEL_ID'])
ADMIN_ID = int(os.environ['ADMIN_ID'])

bot = telebot.TeleBot(BOT_TOKEN)
conn = sqlite3.connect('db.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS products
               (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, name TEXT, price TEXT, photo TEXT)''')
conn.commit()

# 2. قاموس الكلمات - تكدر تضيف كلمات براحتك
KEYWORDS = {
    'كيك وحلويات': ['كيك', 'كعك', 'حلويات', 'بقلاوة', 'معمول', 'كاتو', 'دونات'],
    'البان واجبان': ['لبن', 'جبن', 'جبنة', 'حليب', 'زبادي', 'قشطة', 'قيمر', 'اجبان'],
    'مشروبات': ['ببسي', 'كولا', 'عصير', 'مي', 'ماء', 'سفن', 'ميرندا', 'طاقة'],
    'معلبات': ['تونة', 'فاصوليا', 'حمص', 'فول', 'معلب', 'صلصة', 'مربى', 'شيبس'],
    'منظفات': ['تايت', 'زاهي', 'قاصر', 'شامبو', 'صابون', 'منظف', 'فيري', 'كلوركس'],
    'بهارات': ['فلفل', 'كمون', 'كركم', 'بهار', 'ملح', 'دارسين', 'بابريكا'],
    'كوزمتك': ['مكياج', 'كريم', 'روج', 'كحل', 'مسكارة', 'فاونديشن', 'بودرة', 'عطر', 'لوشن', 'بلسم', 'مناكير']
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

# 3. حفظ من القناة
@bot.channel_post_handler(content_types=['photo'])
def save(message):
    if message.chat.id!= CHANNEL_ID: return
    text = message.caption or ""
    category = detect_category(text)
    price = get_price(text)
    if not price: return bot.send_message(ADMIN_ID, '❌ ما لكيت سعر. اكتب رقم')

    photo = message.photo[-1].file_id
    cur.execute("SELECT COUNT(*) FROM products WHERE category=?", (category,))
    count = cur.fetchone()[0] + 1
    name = f"{category} {count}"

    cur.execute('INSERT INTO products (category, name, price, photo) VALUES (?,?,?,?)', (category, name, price, photo))
    conn.commit()
    bot.send_message(ADMIN_ID, f'✅ حفظت: {name}\n💰 {price} د.ع\n📦 القسم: {category}')

# 4. /start = عرض الأقسام
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    cur.execute('SELECT DISTINCT category FROM products ORDER BY id DESC')
    cats = [row[0] for row in cur.fetchall()]

    if not cats: return bot.send_message(message.chat.id, 'أهلا بيك 👋\nالمنتجات قيد الإضافة')

    for cat in cats:
        markup.add(types.InlineKeyboardButton(cat, callback_data=f'cat_{cat}'))

    bot.send_message(message.chat.id, '*اختر القسم 👇*', reply_markup=markup, parse_mode='Markdown')

# 5. الأزرار: عرض + طلب + حذف للأدمن
@bot.callback_query_handler(func=lambda call: True)
def buttons(call):
    user_id = call.from_user.id
    is_admin = user_id == ADMIN_ID

    if call.data.startswith('cat_'):
        cat = call.data[4:]
        cur.execute("SELECT id, name, price, photo FROM products WHERE category=? ORDER BY id DESC", (cat,))
        items = cur.fetchall()

        if not items: return bot.answer_callback_query(call.id, 'ماكو منتجات')

        bot.edit_message_text(f'*قسم {cat}*', call.message.chat.id, call.message.message_id, parse_mode='Markdown')

        for pid, name, price, photo in items:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton('🛒 اطلب الان', callback_data=f'order_{pid}'))
            if is_admin:
                markup.add(types.InlineKeyboardButton('🗑️ حذف', callback_data=f'del_{pid}'))

            bot.send_photo(call.message.chat.id, photo, caption=f'💰 *السعر: {price} د.ع*',
                           reply_markup=markup, parse_mode='Markdown')

    elif call.data.startswith('order_'):
        pid = call.data.split('_')[1]
        cur.execute("SELECT name, price FROM products WHERE id=?", (pid,))
        name, price = cur.fetchone()
        user = call.from_user
        username = f'@{user.username}' if user.username else user.first_name
        bot.send_message(ADMIN_ID, f'طلب جديد 🔥\n📦 {name}\n💰 {price} د.ع\n👤 {username}\n🆔 {user.id}')
        bot.answer_callback_query(call.id, 'تم ارسال طلبك!')

    elif call.data.startswith('del_'):
        if not is_admin: return bot.answer_callback_query(call.id, 'ما عندك صلاحية')
        pid = call.data.split('_')[1]
        cur.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        bot.answer_callback_query(call.id, 'تم الحذف')
        bot.delete_message(call.message.chat.id, call.message.message_id)

print("البوت شغال...")
bot.infinity_polling()
