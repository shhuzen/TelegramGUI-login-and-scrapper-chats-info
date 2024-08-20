import telebot

from credentials import BOT_TOKEN
from flask import Flask,render_template,request,jsonify,redirect
from sqlalchemy.orm import Session
from database import Group,SessionLocal


    
app = Flask('',static_url_path='', 
            static_folder='templates/static')





bot = telebot.TeleBot(BOT_TOKEN)



# @bot.message_handler(func=lambda message: message.forward_from_chat is not None)
# def handle_forwarded_message(message):
#     # Извлекаем информацию оригинального чата, откуда было переслано сообщение
#     original_chat_id = message.forward_from_chat.id
#     original_chat_title = message.forward_from_chat.title  # Название чата
    
#     bot.send_message(message.chat.id, f"Это сообщение было переслано из чата '{original_chat_title}' с ID: {original_chat_id}")

# @bot.message_handler(func=lambda message: True)
# def handle_all_messages(message):
#     bot.send_message(message.chat.id, f"{ message} Отправьте мне пересланное сообщение, чтобы увидеть, откуда оно было отправлено.")
    
@bot.message_handler(commands=['start'])
def handle_start(message):
    session: Session = SessionLocal()
    user_id = message.from_user.id
    group_id = message.chat.id
    
  
    # Поиск группы в базе данных
    group = session.query(Group).filter(Group.id == group_id).first()
    
    if not group:
        new_group = Group(id=group_id, set_by_id=user_id, bot_ID='')
        session.add(new_group)
        session.commit()
        bot.send_message(message.chat.id, f"Группа успешно добавлена в БД! напиште /app для получение ссылки")
        session.close()

    else:
        bot.send_message(message.chat.id, f"Группа уже есть в БД! напишите /app для получение ссылки")
        session.close()



@bot.message_handler(commands=['app'])
def handle_admin(message):
        session: Session = SessionLocal()
        group_id = message.chat.id
        group = session.query(Group).filter(Group.id == group_id).first()
        # info = {'groupid':group.id,'userid':message.from_user.id}
        # инлайн-кнопки с ссылкой
        # web_app_info = telebot.types.WebAppInfo(url)group
       
        if not hasattr(group,'id'):
                url_button = telebot.types.InlineKeyboardButton(text="Открыть веб-приложение",url=f't.me/userinfomartioncheckBot/app?startapp')
                 # Добавление инлайн-клавиатуры
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(url_button)
                
                # Отправка сообщения с инлайн-кнопкой
                bot.send_message(message.chat.id, "Вы можете открыть веб-приложение, нажав на кнопку ниже:", reply_markup=markup)
                # bot.send_message(message.chat.id, "Если не работают кнопки! перейдите в профиль бота и начните общение")

        else:
                url_button = telebot.types.InlineKeyboardButton(text="Открыть веб-приложение", url=f't.me/userinfomartioncheckBot/app?startapp={group.id}')

                # Добавление инлайн-клавиатуры
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(url_button)
                
                # Отправка сообщения с инлайн-кнопкой
                bot.send_message(message.chat.id, "Вы можете открыть веб-приложение, нажав на кнопку ниже:", reply_markup=markup)
      

# @bot.message_handler(commands=['setbotID'])
# def handle_set_bot_id(message):
#     session: Session = SessionLocal()
#     user_id = message.from_user.id
#     group_id = message.chat.id
    
#     # Извлечение bot_ID из команды
#     bot_ID = message.text[len('/setbotID '):].strip()
    
#     # Поиск группы в базе данных
#     group = session.query(Group).filter(Group.id == group_id).first()
    
#     if not group:
#         new_group = Group(id=group_id, set_by_id=user_id, bot_ID=bot_ID)
#         session.add(new_group)
#         session.commit()
#         bot.send_message(message.chat.id, f"Новая группа!bot_ID установлен {bot_ID}!")
#     else:
#         group.bot_ID = bot_ID
#         session.commit()
#         bot.send_message(message.chat.id, f'Изменен bot_ID {bot_ID}')
    
    # session.close()

@app.route('/')
def index():
   
        return render_template('index.html', )








@app.route('/group', methods=['GET'])
def get_group():
    chat_id = request.args.get('chat_id')
    if not chat_id:
        return jsonify({"error": "chat_id parameter is required"}), 400

    session = SessionLocal()
    group = session.query(Group).filter(Group.id == chat_id).first()
    session.close()
    if group:
        return jsonify({
            "id": group.id,
            "set_by_id": group.set_by_id,
            "bot_ID": group.bot_ID
        })
    else:
        return jsonify({"error": "Не задан!"}), 404