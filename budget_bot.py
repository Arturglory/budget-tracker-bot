import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
import sqlite3
from datetime import datetime
import matplotlib.pyplot as plt
import os

with open("token.txt", "r") as file:
    BOT_TOKEN = file.read().strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Настройка базы данных SQLite
def init_db():
    conn = sqlite3.connect("data/budget.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, 
                  category TEXT, type TEXT, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

class TransactionStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()

# Функция для создания главной клавиатуры
def get_main_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Добавить доход"), types.KeyboardButton(text="Добавить расход")],
            [types.KeyboardButton(text="Баланс"), types.KeyboardButton(text="Статистика")]
        ],
        resize_keyboard=True
    )

# Функция для создания клавиатуры с категориями и кнопкой "Главное меню"
def get_category_keyboard(type):
    if type == "income":
        categories = ["Зарплата", "Премия"]
    else:
        categories = ["Еда", "Лекарства", "Авто", "Коммунальные", "Отдых"]
    keyboard = [[types.KeyboardButton(text=cat)] for cat in categories]
    keyboard.append([types.KeyboardButton(text="Главное меню")])
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я помогу следить за твоим бюджетом. Выбери действие:", reply_markup=get_main_keyboard())

@dp.message(F.text == "Добавить доход")
async def process_add_income(message: types.Message, state: FSMContext):
    await message.reply("Введи сумму дохода (например, 1000):", reply_markup=get_category_keyboard("income"))
    await state.set_state(TransactionStates.waiting_for_amount)
    await state.update_data(transaction_type="income")

@dp.message(F.text == "Добавить расход")
async def process_add_expense(message: types.Message, state: FSMContext):
    await message.reply("Введи сумму расхода (например, 500):", reply_markup=get_category_keyboard("expense"))
    await state.set_state(TransactionStates.waiting_for_amount)
    await state.update_data(transaction_type="expense")

@dp.message(TransactionStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    if message.text == "Главное меню":
        await message.reply("Возвращаюсь в главное меню.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        user_data = await state.get_data()
        transaction_type = user_data["transaction_type"]
        await message.reply("Выбери категорию или напиши свою:", reply_markup=get_category_keyboard(transaction_type))
        await state.set_state(TransactionStates.waiting_for_category)
    except ValueError:
        await message.reply("Пожалуйста, введи корректное число!")

@dp.message(TransactionStates.waiting_for_category)
async def process_category(message: types.Message, state: FSMContext):
    if message.text == "Главное меню":
        await message.reply("Возвращаюсь в главное меню.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    category = message.text
    user_data = await state.get_data()
    amount = user_data["amount"]
    transaction_type = user_data["transaction_type"]
    user_id = message.from_user.id
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("data/budget.db")
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, amount, category, type, date) VALUES (?, ?, ?, ?, ?)",
              (user_id, amount if transaction_type == "income" else -amount, category, transaction_type, date))
    conn.commit()
    conn.close()
    await message.reply(f"{transaction_type.capitalize()} {abs(amount)} грн. ({category}) записан.", reply_markup=get_main_keyboard())
    await state.clear()

# Показать баланс
@dp.message(F.text == "Баланс")
async def show_balance(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("data/budget.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ?", (user_id,))
    balance = c.fetchone()[0] or 0
    conn.close()
    await message.reply(f"Текущий баланс: {balance:.2f} грн.", reply_markup=get_main_keyboard())

@dp.message(F.text == "Статистика")
async def show_stats(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("data/budget.db")
    c = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    c.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = ? AND date LIKE ? AND type = 'income' GROUP BY category",
              (user_id, f"{current_month}%"))
    incomes = c.fetchall()
    c.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = ? AND date LIKE ? AND type = 'expense' GROUP BY category",
              (user_id, f"{current_month}%"))
    expenses = c.fetchall()
    conn.close()

    stats_text = f"Статистика за {current_month}:\n\n"
    if incomes:
        total_income = sum(amount for _, amount in incomes)
        stats_text += "Доходы:\n"
        for category, amount in incomes:
            stats_text += f"{category}: {amount:.2f} грн.\n"
        stats_text += f"Итого доходы: {total_income:.2f} грн.\n\n"
    else:
        stats_text += "Доходов за этот месяц нет.\n\n"
    if expenses:
        total_expense = sum(-amount for _, amount in expenses)
        stats_text += "Расходы:\n"
        for category, amount in expenses:
            stats_text += f"{category}: {-amount:.2f} грн.\n"
        stats_text += f"Итого расходы: {total_expense:.2f} грн.\n"
    else:
        stats_text += "Расходов за этот месяц нет.\n"

    categories, amounts = [], []
    if incomes:
        for cat, amt in incomes:
            categories.append(f"Доход: {cat}")
            amounts.append(amt)
    if expenses:
        for cat, amt in expenses:
            categories.append(f"Расход: {cat}")
            amounts.append(-amt)
    if not categories:
        await message.reply("Нет транзакций за этот месяц.", reply_markup=get_main_keyboard())
        return

    plt.figure(figsize=(10, 6))
    plt.bar(categories, amounts, color=['green' if x > 0 else 'red' for x in amounts])
    plt.title(f"Доходы и расходы за {current_month}")
    plt.ylabel("Сумма (грн.)")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig("data/transaction_chart.png")
    plt.close()

    await message.reply(stats_text, reply_markup=get_main_keyboard())
    with open("data/transaction_chart.png", "rb") as photo:
        await bot.send_photo(message.chat.id, photo)
    os.remove("data/transaction_chart.png")

@dp.message(F.text == "Главное меню")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.clear()
    await message.reply("Возвращаюсь в главное меню.", reply_markup=get_main_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())