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

# انشاء الجدول
cur.execute('''CREATE TABLE IF NOT EXISTS products
               (id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                name TEXT,
                description TEXT,
                price TEXT,
                photo TEXT)''')
conn.commit()

# ترقية الجدول تلقائياً اذا ضفت حقول جديدة بعدين
def upgrade_db():
    cur.execute("PRAGMA table_info(products)")
    columns = [row[1] for row in cur.fetchall()]

    if 'description' not in columns:
        cur.execute("ALTER TABLE products ADD COLUMN description TEXT DEFAULT ''")
        print('Added description column')

    # تقدر تضيف حقول جديدة هنا بعدين
    # if 'stock' not in columns:
    # cur.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")

    conn.commit()

upgrade_db()

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
    match = re.search(r'(\d[\d,]*)\s*(د\.ع|دينار|الف|الفين)?', text)
    if match:
        price = match.group(1).replace(',', '')
        unit = match.group(2)
        if unit and 'الف' in unit:
            if 'الفين' in unit:
                price = str(int(price) * 2000)
            else:
                price = str(int(price) * 1000)
        return price
    return None

def extract_name_desc(text):
    text_without_price = re.sub(r'\d[\d,]*\s*(د\.ع|دينار|الف|الفين)?', '', text).strip()
    lines = [line.strip() for line in text_without_price.split('\n') if line.strip()]

    if not lines:
        return 'بدون اسم', ''

    name = lines[0][:50]
    description = '\n'.join(lines[1:])[:300]
    return name or 'بدون اسم', description

@bot.channel_post_handler(content_types=['photo'])
def save(message):
    if message.chat.id!= CHANNEL_ID:
        return

    text = message.caption or ""
    category = detect_category(text)
    price = get_price(text)
    name, description = extract_name_desc(text)

    if not price:
        price = 'غير محدد'
        for admin in ADMIN_IDS:
            bot.send_message(admin, f'⚠️ تنبيه: منتج بدون سعر\n📦 {name}\n📝 {text[:100]}')

    photo = message.photo[-1].file_id
    cur.execute("INSERT INTO products (category, name, description, price, photo) VALUES (?,?,?,?,?)",
                (category, name, description, price, photo))
    conn.commit()
    product_id = cur.lastrowid

    notif = f'✅ تم حفظ منتج جديد #{product_id}\n📦 القسم: {category}\n🏷️ {name}\n💰 {price}'
    if price!= 'غير محدد':
        notif += ' د.ع'
    if description:
        notif += f'\n📝 {description[:50]}...'

    for admin in ADMIN_IDS:
        bot.send_message(admin, notif)

def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    cur.execute('SELECT DISTINCT category FROM products ORDER BY category')
    cats = [row[0] for row in cur.fetchall()]

    if not cats:
        markup.add(types.InlineKeyboardButton('لا توجد منتجات حالياً', callback_data='none'))
    else:
        for cat in cats:
            cur.execute('SELECT COUNT(*) FROM products WHERE category=?', (cat,))
            count = cur.fetchone()[0]
            markup.add(types.InlineKeyboardButton(f'{cat} ({count})', callback_data=f'cat_{cat}'))

    if SUPPORT_USERNAME:
        markup.add(types.InlineKeyboardButton('📞 استفسار او طلب جملة', url=f'https://t.me/{SUPPORT_USERNAME}'))

    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
                     'اهلاً بيك 👋\nاختر القسم الي تريده:',
                     reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def show_category(call):
    category = call.data[4:]
    cur.execute('SELECT id, name, price, photo, description FROM products WHERE category=? ORDER BY id DESC LIMIT 10', (category,))
    products = cur.fetchall()

    if not products:
        bot.answer_callback_query(call.id, 'لا توجد منتجات بهذا القسم')
        return

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f'📦 منتجات قسم: {category}')

    for pid, name, price, photo, description in products:
        caption = f'🏷️ {name}\n💰 السعر: {price}'
        if price!= 'غير محدد':
            caption += ' د.ع'
        else:
            caption += '\n❗ السعر عند الاستفسار'

        if description:
            caption += f'\n📝 {description}'

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('🛒 اطلب الان', callback_data=f'order_{pid}'))

        # اذا ادمن، نضيف ازرار تعديل وحذف
        if call.from_user.id in ADMIN_IDS:
            markup.add(
                types.InlineKeyboardButton('✏️ تعديل', callback_data=f'edit_{pid}'),
                types.InlineKeyboardButton('🗑️ حذف', callback_data=f'del_{pid}')
            )

        bot.send_photo(call.message.chat.id, photo, caption=caption, reply_markup=markup)

    back = types.InlineKeyboardMarkup()
    back.add(types.InlineKeyboardButton('🔙 رجوع للقائمة', callback_data='back_menu'))
    bot.send_message(call.message.chat.id, 'اختر منتج او ارجع للقائمة', reply_markup=back)

@bot.callback_query_handler(func=lambda call: call.data == 'back_menu')
def back_to_menu(call):
    bot.edit_message_text('اهلاً بيك 👋\nاختر القسم الي تريده:',
                          call.message.chat.id,
                          call.message.message_id,
                          reply_markup=main_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('order_'))
def order_product(call):
    pid = int(call.data[6:])
    cur.execute('SELECT name, price, category FROM products WHERE id=?', (pid,))
    product = cur.fetchone()

    if not product:
        bot.answer_callback_query(call.id, 'المنتج غير موجود', show_alert=True)
        return

    name, price, category = product
    user = call.from_user

    text = f'🛒 طلب جديد\n\n👤 العميل: @{user.username or user.first_name}\n🆔 {user.id}\n\n📦 المنتج: {name}\n📂 القسم: {category}\n💰 السعر: {price}'
    if price!= 'غير محدد':
        text += ' د.ع'

    for admin in ADMIN_IDS:
        bot.send_message(admin, text)

    bot.answer_callback_query(call.id, 'تم ارسال طلبك للادارة ✅', show_alert=True)

# تعديل المنتج للادمن
@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def edit_product(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, 'ماعندك صلاحية', show_alert=True)
        return

    pid = int(call.data[5:])
    cur.execute('SELECT name, price, description FROM products WHERE id=?', (pid,))
    product = cur.fetchone()

    if not product:
        bot.answer_callback_query(call.id, 'المنتج غير موجود', show_alert=True)
        return

    name, price, description = product
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('💰 تعديل السعر', callback_data=f'editprice_{pid}'))
    markup.add(types.InlineKeyboardButton('📝 تعديل الوصف', callback_data=f'editdesc_{pid}'))
    markup.add(types.InlineKeyboardButton('🔙 رجوع', callback_data='back_menu'))

    bot.send_message(call.message.chat.id,
                     f'✏️ تعديل المنتج #{pid}\n\n🏷️ {name}\n💰 {price}\n📝 {description or "لا يوجد وصف"}\n\nاختر شنو تريد تعدل:',
                     reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('editprice_'))
def edit_price_start(call):
    pid = int(call.data[10:])
    msg = bot.send_message(call.message.chat.id, f'ارسل السعر الجديد للمنتج #{pid}\nارسل 0 اذا تريد تخليه "غير محدد"')
    bot.register_next_step_handler(msg, lambda m: save_new_price(m, pid))
    bot.answer_callback_query(call.id)

def save_new_price(message, pid):
    new_price = message.text.strip()
    if new_price == '0':
        new_price = 'غير محدد'
    else:
        new_price = re.sub(r'[^\d]', '', new_price) # بس ارقام

    cur.execute("UPDATE products SET price=? WHERE id=?", (new_price, pid))
    conn.commit()
    bot.send_message(message.chat.id, f'✅ تم تحديث السعر الى: {new_price}')

@bot.callback_query_handler(func=lambda call: call.data.startswith('editdesc_'))
def edit_desc_start(call):
    pid = int(call.data[9:])
    msg = bot.send_message(call.message.chat.id, f'ارسل الوصف الجديد للمنتج #{pid}')
    bot.register_next_step_handler(msg, lambda m: save_new_desc(m, pid))
    bot.answer_callback_query(call.id)

def save_new_desc(message, pid):
    new_desc = message.text.strip()[:300]
    cur.execute("UPDATE products SET description=? WHERE id=?", (new_desc, pid))
    conn.commit()
    bot.send_message(message.chat.id, f'✅ تم تحديث الوصف')

# حذف المنتج
@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def delete_product(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, 'ماعندك صلاحية', show_alert=True)
        return

    pid = int(call.data[4:])
    cur.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    bot.answer_callback_query(call.id, 'تم حذف المنتج ✅', show_alert=True)
    bot.delete_message(call.message.chat.id, call.message.message_id)

# امر النسخ الاحتياطي للادمن
@bot.message_handler(commands=['backup'])
def backup(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        with open('db.db', 'rb') as db_file:
            bot.send_document(message.chat.id, db_file, caption='📦 نسخة احتياطية من قاعدة البيانات')
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ خطأ: {e}')

if __name__ == '__main__':
    print('Bot is running...')
    bot.infinity_polling()
