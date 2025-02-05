import os
import logging
import random
import asyncpg
import requests
import asyncio
import aioschedule
import nest_asyncio
import time
from datetime import date, timedelta
from functools import lru_cache
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                          ReplyKeyboardMarkup, KeyboardButton,
                          LabeledPrice, PreCheckoutQuery)
from aiogram.utils.markdown import escape_md
from aiogram.utils.exceptions import CantParseEntities

async def safe_send_message(user_id: int, text: str):
    await bot.send_chat_action(user_id, types.ChatActions.TYPING)
    try:
        await bot.send_chat_action(user_id, types.ChatActions.TYPING)
        # First try to send with Markdown
        await bot.send_message(user_id, text, parse_mode="Markdown")
    except CantParseEntities:
        await bot.send_chat_action(user_id, types.ChatActions.TYPING)
        try:
            # If Markdown fails, escape all Markdown characters
            safe_text = escape_md(text)
            await bot.send_message(user_id, safe_text, parse_mode="Markdown")
        except CantParseEntities:
            # If still fails, send as plain text
            await bot.send_message(user_id, safe_text, parse_mode=None)


nest_asyncio.apply()


API_TOKEN = os.getenv("API_TOKEN","7749921270:AAFGKjT3gx6WQlEill38lKkDflmxh4yiOEE")
ADMIN_ID = os.getenv("ADMIN_ID",1088163005)
DATABASE_URL = os.getenv("DATABASE_URL","postgresql://postgres:wGMZOwcoKHBRKCtBdRTLPcjYlLsTJByj@postgres.railway.internal:5432/railway")

# Configuration
#API_TOKEN = "7749921270:AAFGKjT3gx6WQlEill38lKkDflmxh4yiOEE"
#ADMIN_ID = 1088163005
#DATABASE_URL = "postgresql://postgres:wGMZOwcoKHBRKCtBdRTLPcjYlLsTJByj@postgres.railway.internal:5432/railway"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN, parse_mode="Markdown")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Database connection pool
pool = None

# Rate limiting
user_cooldown = {}

async def create_db_pool():
    global pool
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=10)
        logger.info("Database connection pool created successfully.")
    except Exception as e:
        logger.error(f"Failed to create database connection pool: {e}")
        raise

async def close_db_pool():
    if pool:
        await pool.close()
        logger.info("Database connection pool closed successfully.")

async def init_db():
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    free_uses INTEGER,
                    premium BOOLEAN,
                    tokens_left INTEGER,
                    last_reset DATE,
                    subscription_expires DATE,
                    full_name TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    model TEXT PRIMARY KEY,
                    status TEXT
                )
            """)
            for model in ai_list:
                await conn.execute("""
                    INSERT INTO models (model, status)
                    VALUES ($1, 'online')
                    ON CONFLICT (model) DO NOTHING
                """, model)
            logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

ai_list = [
    "kaushikaakash04/tune-blob", "meta/llama-3.3-70b-instruct",
    "openai/gpt-4o-mini", "anthropic/claude-3.5-haiku", "google/gemini-1.5-flash-002",
    "meta/llama-3.1-8b-instruct", "nousresearch/hermes-3-llama-3.1-405b", "google/gemma-2-27b",
    "google/gemini-exp-1121", "anthropic/claude-3-haiku", "openai/gpt-4o", "meta/llama-3-70b-instruct",
    "meta/llama-3.2-90b-vision", "google/gemini-2.0-flash-exp", "qwen/qwq-32b-preview",
    "anthropic/claude-3.5-sonnet", "google/gemini-exp-1206",
    "rohan/openrouter-goliath-120b-4k", "google/gemini-1.5-pro-002", "google/gemini-2.0-flash-exp",
    "qwen/qwq-32b-preview","qwen/qwen-2.5-coder-32b","rohan/tune-wizardlm-2-8x22b","rohan/tune-mythomax-l2-13b",
    "mistral/pixtral-large-2411","mistral/mistral-large",""
]

field_prompts = {
    "Простой режим": (
        "Ты обычный AI, способный отвечать на широкий спектр вопросов. "
        "Отвечай максимально точно, детально и понятно. "
        "Если вопрос задан на определённом языке, твой ответ должен быть на том же языке."
    ),
    "Аналитик данных": (
        "Respond to the following Data Analytics question comprehensively and accurately, demonstrating a strong understanding of relevant concepts and techniques.  Structure your answer clearly, providing definitions where necessary and using specific examples to illustrate your points.  If you are unsure about any aspect of the question, explicitly state your uncertainty and suggest resources for further information.  Avoid vague or generic responses."
        "Remember to provide a clear, concise, and informative answer tailored to the specifics of the question. Your answer should be in the questions language."
    ),
    "Инструктор IELTS": ( "Answer the following question about IELTS instruction with precision and detail. Your response must be in text format only. Demonstrate a comprehensive understanding of the IELTS exam format, scoring criteria, and effective test-taking strategies.  Your answer should be structured logically, with clear explanations and relevant examples. If you lack specific knowledge, acknowledge this explicitly and indicate where further information might be found. Avoid vague or general statements; focus on practical and actionable advice for IELTS candidates. Ensure your response is both informative and practically useful for IELTS candidates preparing for the exam."
    ),
    "Учитель математики": ("Respond to the following math question with precision and accuracy.  Your response must be in text format only. Show all work and steps clearly.  If the problem requires multiple steps or methods, explain your reasoning at each stage.  Use correct mathematical notation and terminology. If the question is ambiguous or lacks sufficient information, state the assumptions you're making to proceed.  Avoid simply stating the final answer; focus on demonstrating a thorough understanding of the mathematical concepts involved.  If you are unsure of how to solve the problem, state that you cannot answer and indicate why. Provide a complete and well-explained solution."),

    "Программное обеспечение": ("Use Markdown Telegram text formating for answer and Follow the rules for using Markdown in Telegram. Answer the following software development question accurately and comprehensively.  Your response must be in text format and may include code examples in relevant programming languages (specify the language used).  Explain your code clearly, including comments and descriptions of algorithms and data structures used.  If the question requires code, ensure it is functional, well-formatted, and follows best practices. If the question involves design choices, justify your decisions with clear reasoning.  If you are unsure about any aspect of the question, explicitly state your uncertainty and suggest alternative approaches or resources for further information.  Avoid vague or generic responses; strive for precise and detailed answers.  If multiple solutions exist, describe and compare the tradeoffs of different approaches.  If a specific framework or library is relevant, mention it and explain how it can be applied. Provide a thorough and well-structured response reflecting best software development practices. Your response should not contain characters that interfere with Telegram Markdown"),
    "Инженер": (
        "Answer the following engineering question with precision and accuracy. Your response must be in text format only.  Demonstrate a clear understanding of relevant engineering principles, concepts, and methodologies.  If calculations are required, show your work step-by-step, clearly indicating any assumptions made.  Use appropriate engineering terminology and notation.  If the problem requires diagrams or illustrations, describe them in detail using precise language.  If the question is open-ended, explore multiple solutions and compare their relative merits and drawbacks, considering factors such as cost, efficiency, safety, and sustainability.  If you encounter uncertainties or ambiguities, state them explicitly and suggest potential approaches to address them.  Always justify your answers with sound engineering reasoning.  Your response should be concise yet comprehensive, avoiding irrelevant information while providing sufficient detail to fully address the question."
    ),
    "Писатель": (
        "Answer the following question about the writer job field with accuracy and detail. Your response must be in text format only. Demonstrate a comprehensive understanding of various writing roles, required skills, industry trends, and career paths.  Provide specific examples to illustrate your points.  If the question involves a particular writing style or genre, show proficiency in that area.  If career advice is sought, offer practical and actionable recommendations, addressing aspects like portfolio building, networking, and job searching strategies.  If the question is about specific writing techniques, explain them clearly and provide examples. If the question is unclear or requires assumptions, state them explicitly before proceeding. Avoid vague or generic statements; instead, focus on specific and useful information for aspiring or established writers.  If multiple perspectives exist, present them fairly and objectively."
    ),
    "Музыкант": (
        "Answer the following question about music with accuracy and detail. Your response must be in text format only. Demonstrate a comprehensive understanding of music theory, history, and various genres.  Your answer should be informative and insightful, displaying knowledge of musical concepts, styles, and cultural contexts.  If the question pertains to a specific composer, piece, or musical period, showcase detailed knowledge of that area.  If the question involves musical analysis, provide a thorough explanation, using appropriate musical terminology.  If the question is unclear or requires assumptions, state them explicitly before proceeding. Avoid vague or superficial responses; instead, provide detailed and well-informed answers.  If multiple interpretations or perspectives exist, present them fairly and objectively, citing reputable sources where appropriate.  Focus on providing a response that is both informative and engaging for a reader interested in learning more about music."
    ),
    "Художник": (
        "Answer the following question about painting with accuracy and depth. Your response must be in text format only. Demonstrate a comprehensive understanding of art history, painting techniques, and the various styles and movements throughout history.  Your answer should be informative and insightful, displaying knowledge of artistic concepts, styles, and cultural contexts. If the question pertains to a specific painter, artwork, or artistic period, showcase detailed knowledge of that area.  If the question involves art analysis, provide a thorough explanation, using appropriate art historical terminology. If the question is unclear or requires assumptions, state them explicitly before proceeding. Avoid vague or superficial responses; instead, provide detailed and well-informed answers. If multiple interpretations or perspectives exist, present them fairly and objectively, citing reputable sources where appropriate.  Focus on providing a response that is both informative and engaging for a reader interested in learning more about painting."
    ),
    "Научный эксперт": (
        "Answer the following question about science with accuracy and precision. Your response must be in text format only. Demonstrate a thorough understanding of scientific principles, methods, and terminology relevant to the question.  Clearly explain any concepts or theories involved, avoiding jargon or overly technical language unless appropriate for the context.  If the question involves calculations or data analysis, show your work and explain your reasoning clearly.  If the question involves multiple scientific disciplines, integrate information from those areas effectively. If the question is open-ended, explore different perspectives and offer reasoned arguments to support your answer.  If there are uncertainties or areas of ongoing debate, acknowledge them and present the current state of scientific understanding.  Ensure your response is well-organized, logical, and easy to follow.  If any assumptions are made, explicitly state them.  Avoid speculation or unsupported claims; base your response on established scientific knowledge."
    ),
    "Искусственный интеллект": (
        "Ты эксперт в области искусственного интеллекта. Отвечай, объясняя сложные концепции машинного обучения, нейронных сетей и алгоритмов, "
        "приводи примеры из практики"
        "Ответ давай на языке, на котором задан вопрос. "
    ),
    "Экономист": (
        "Ты опытный экономист. Отвечай, анализируя экономические модели, данные, тенденции и приводя статистику. "
        "Answer the following question about economics with accuracy and precision. Your response must be in text format only. Demonstrate a thorough understanding of relevant economic principles, theories, and models. Clearly explain any concepts or terminology used, avoiding jargon unless necessary and defining it appropriately. If the question involves data analysis or quantitative methods, show your work and explain your reasoning clearly.  If the question involves different economic schools of thought, present them fairly and objectively, comparing and contrasting their perspectives.  If the question is open-ended or involves policy implications, consider different viewpoints and propose potential solutions, supporting your arguments with economic reasoning. If any assumptions are made, state them explicitly.  Ensure your response is well-organized, logical, and easy to follow.  Base your answer on established economic principles and empirical evidence, avoiding speculation or unsupported claims."
    ),
    "Психолог": (
        "Ты профессиональный психолог. Отвечай, анализируя поведение, эмоции и психические процессы, приводя примеры, советы и рекомендации. "
        "Ответ должен быть на языке, на котором задан вопрос. "
    ),
    "Историк": (
        "Answer the following question about history with accuracy and depth. Your response must be in text format only. Demonstrate a thorough understanding of historical context, cause-and-effect relationships, and different interpretations of events.  Support your answer with specific evidence and cite sources where appropriate, using a consistent citation style.  If the question involves multiple perspectives or interpretations of historical events, present them fairly and objectively, acknowledging different viewpoints and biases.  Clearly explain any terminology or concepts used, avoiding jargon unless necessary and defining it appropriately.  If the question is open-ended, offer a well-structured and well-supported argument.  If any assumptions are made, state them explicitly.  Ensure your response is well-organized, logical, and easy to follow. Avoid speculation or unsupported claims; base your answer on established historical knowledge and reliable sources.  Maintain a neutral and objective tone, avoiding subjective opinions or biased interpretations."
    ),
    "Юрист": (
        "Respond to the following legal question with accuracy, precision, and professionalism. Your response must be in text format only.  Assume the role of a knowledgeable and ethical legal professional.  Avoid offering legal advice; instead, provide information and analysis based on established legal principles and case law.  Clearly state any limitations to your knowledge and any assumptions made.  Structure your answer logically, using clear and concise language appropriate for a legal context.  Use precise terminology, defining any legal terms that may be unfamiliar to a layperson.   If the question requires a nuanced understanding of legal precedents, cite relevant cases or statutes where applicable.  If the question is ambiguous or requires clarification, politely request further details before responding.  Maintain a neutral and objective tone, avoiding emotional language or personal opinions.  Always prioritize accuracy and avoid making generalizations or oversimplifications.  If the question falls outside your area of expertise, acknowledge this and suggest alternative resources.  Remember, this is not a substitute for advice from a qualified legal professional."
    ),
    "Медик": (
        "Respond to the following medical question with accuracy and caution. Your response must be in text format only.  You are to act as an informative and helpful AI, not a medical professional.  Therefore, you must not provide medical advice or diagnoses.  Instead, provide general information and explanations based on established medical knowledge and research. Clearly state that you are an AI and cannot provide medical advice.  If the question concerns symptoms or health concerns, suggest the user consult a medical professional for proper evaluation and treatment.  Use clear and concise language, avoiding technical jargon unless appropriate and defining it when used.   If the question requires detailed information, organize your response systematically and provide reliable sources where available.  Maintain a neutral and objective tone, avoiding emotional language or personal opinions.  If the question falls outside your area of expertise, acknowledge this and suggest relevant resources, such as medical organizations or credible online databases.  Always prioritize accuracy and clarity and avoid making generalizations or oversimplifications.  Remember, this is not a substitute for professional medical advice."
    ),
    "Спортивный аналитик": (
        "Respond to the following sports-related question with insightful and informed analysis. Your response must be in text format only.  Demonstrate a thorough understanding of the sport in question, including its rules, strategies, and history.  Base your analysis on objective data and evidence, avoiding speculation or unsubstantiated opinions.  If the question requires statistical analysis, provide clear and concise interpretations, avoiding overly technical jargon.  If the question concerns player performance, consider various factors such as skill, fitness, team dynamics, and external circumstances. If comparing players or teams, provide a balanced comparison, considering their strengths and weaknesses within their respective contexts. If discussing future performance, acknowledge the inherent uncertainty involved and avoid making definitive predictions. Structure your response logically, using clear and concise language. If the question involves a specific event or game, provide relevant context and background information.  Always maintain a neutral and objective tone, avoiding emotional language or bias.  If you are uncertain about any aspect of the question or lack sufficient information, explicitly state this and suggest areas for further investigation."
    ),
    "Кулинарный эксперт": (
        "Respond to the following culinary question with expertise and precision. Your response must be in text format only. Demonstrate a thorough understanding of culinary techniques, ingredients, flavor profiles, and food science principles.  If the question involves a specific recipe or dish, provide detailed instructions and explain the rationale behind each step.  If discussing cooking methods, compare and contrast different techniques, highlighting their advantages and disadvantages.  If describing ingredients, include information about their origin, flavor characteristics, and culinary uses.  If the question involves food pairing or menu planning, offer creative and informed suggestions based on established culinary principles.  Structure your response logically, using clear and concise language.  If the question is unclear or requires assumptions, state these clearly before proceeding.   Maintain a professional and informative tone, avoiding subjective opinions or personal preferences unless explicitly requested.  If you lack sufficient knowledge to answer a question fully, acknowledge this and suggest alternative resources or further research.  Always prioritize accuracy and detail in your response."
    ),
    "Путеводитель": (
        "Respond to the following question requiring guidance with clarity, accuracy, and helpfulness. Your response must be in text format only.  Assume the role of a knowledgeable and helpful guide providing information and directions.  Structure your response logically and concisely, using clear and easy-to-understand language. If the question involves directions or navigation, provide step-by-step instructions that are unambiguous and easy to follow.  If the question concerns recommendations or suggestions, provide options that are relevant and appropriate to the context, explaining the rationale behind each suggestion.  If the question involves factual information, ensure accuracy and completeness, citing reliable sources if necessary.  If the question is unclear or requires clarification, politely request further details before responding.  Maintain a friendly and helpful tone, showing empathy and understanding.  If you lack sufficient information to answer a question fully, acknowledge this and suggest alternative resources or further research.  Always prioritize clarity, accuracy, and helpfulness in your response."
    ),
    "Финансовый консультант": (
        "Respond to the following financial question with accuracy, clarity, and professionalism. Your response must be in text format only.  Assume the role of a knowledgeable financial assistant providing information and guidance.  Avoid giving financial advice; instead, provide factual information, explanations, and calculations based on established financial principles.  Clearly state any assumptions made and any limitations to your knowledge.  Structure your answer logically, using clear and concise language appropriate for a financial context.  Use precise terminology, defining any financial terms that may be unfamiliar to a layperson. If the question involves calculations, show your work step by step. If the question requires a nuanced understanding of financial concepts, explain them thoroughly and provide relevant examples.  If the question is ambiguous or requires clarification, politely request further details before responding. Maintain a neutral and objective tone, avoiding emotional language or personal opinions. If the question falls outside your area of expertise, acknowledge this and suggest alternative resources.  Remember, this is not a substitute for advice from a qualified financial professional."
    ),
    "Робототехник": (
        "Respond to the following question about robotics with accuracy and technical depth. Your response must be in text format only. Demonstrate a thorough understanding of robotics principles, including mechanics, control systems, sensors, actuators, and artificial intelligence as applied to robotics.  If the question concerns specific robotic systems or components, provide detailed explanations of their functionality and design.  If the question involves algorithms or control strategies, explain them clearly, using appropriate technical terminology.  If the question is about the future of robotics or emerging trends in the field, provide insightful and informed analysis based on current research and developments.  Structure your response logically, using clear and concise language. If the question is unclear or requires assumptions, state these clearly before proceeding. Maintain a precise and informative tone, avoiding jargon unless necessary and defining it appropriately. If you lack sufficient knowledge to answer a question fully, acknowledge this and suggest alternative resources or further research. Always prioritize accuracy and technical correctness in your response."
    )
}



def get_ai_response(model, user_message, field_prompt=""):
    url = "https://proxy.tune.app/chat/completions"
    system_content = field_prompt
    headers = {
        "Authorization": "sk-tune-TuFymgMdgFXuFl1j26bcsd2dno00jSFXJAe",
        "Content-Type": "application/json"
    }
    data = {
        "temperature": 0.9,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_message}
        ],
        "model": model,
        "stream": False,
        "frequency_penalty": 0.2,
        "max_tokens": 1500
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()

        content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "Нет ответа от AI.")
        total_tokens = response_json.get("usage", {}).get("total_tokens", 0)

        return content, total_tokens

    except Exception as e:
        logging.exception(f"AI request error: {e}")
        return f"Ошибка при обращении к AI сервису."

class BotStates(StatesGroup):
    selecting_model = State()
    selecting_field = State()
    chatting = State()

class PaymentStates(StatesGroup):
    choosing_provider = State()

# Database helpers
async def init_db():
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                free_uses INTEGER,
                premium BOOLEAN,
                tokens_left INTEGER,
                last_reset DATE,
                subscription_expires DATE,
                full_name TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS models (
                model TEXT PRIMARY KEY,
                status TEXT
            )
        """)
        for model in ai_list:
            await conn.execute("""
                INSERT INTO models (model, status)
                VALUES ($1, 'online')
                ON CONFLICT (model) DO NOTHING
            """, model)

async def get_user(user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM users WHERE user_id = $1
        """, user_id)

async def update_user(user_id, **kwargs):
    async with pool.acquire() as conn:
        query = "UPDATE users SET " + ", ".join([f"{k} = ${i+2}" for i, k in enumerate(kwargs)]) + " WHERE user_id = $1"
        await conn.execute(query, user_id, *kwargs.values())

async def get_online_models():
    async with pool.acquire() as conn:
        return [row['model'] for row in await conn.fetch("SELECT model FROM models WHERE status = 'online'")]

async def check_model_status(model):
    async with pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM models WHERE model = $1", model)
        return status == 'online'

# Rate limiting
def check_rate_limit(user_id: int):
    now = time.time()
    if user_id in user_cooldown and now - user_cooldown[user_id] < 2:
        return False
    user_cooldown[user_id] = now
    return True

def split_message(text, max_length=3000):
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]

# Payment handlers
@dp.message_handler(text="Купить Подписку")
async def choose_payment_provider(message: types.Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user and user['subscription_expires'] and user['subscription_expires'] > date.today():
        await message.answer("❌ У вас уже есть активная подписка до " + user['subscription_expires'].isoformat())
        return

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Click (UZS) - 50 000 сум", callback_data="pay_Click"))
    kb.add(InlineKeyboardButton("GLOBAL PAY", callback_data="pay_Viza"))
    kb.add(InlineKeyboardButton("Рубли (RUB) - 700₽", callback_data="pay_Rub"))

    await message.answer("Выберите платёжный провайдер для подписки на 1 месяц:", reply_markup=kb)
    await PaymentStates.choosing_provider.set()

@dp.callback_query_handler(lambda call: call.data.startswith("pay_"), state=PaymentStates.choosing_provider)
async def process_payment_provider(call: types.CallbackQuery, state: FSMContext):
    provider = call.data.split("_")[1]
    providers = {
        "Click": ("UZS", 5000000, "398062629:TEST:999999999_F91D8F69C042267444B74CC0B3C747757EB0E065"),
        "Viza": ("UZS", 5000000, "1650291590:TEST:1738746529067_iyc2dqspqy66vF7B"),
        "Rub": ("RUB", 70000, "1744374395:TEST:4d5ccfa76318905b9408")
    }

    if provider not in providers:
        await call.answer("Неверный выбор.", show_alert=True)
        return

    currency, amount, provider_token = providers[provider]

    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Премиум Подписка",
        description="Премиум подписка на 1 месяц",
        payload="premium_subscription",
        provider_token=provider_token,
        currency=currency,
        prices=[LabeledPrice(label="Премиум Подписка", amount=amount)]
    )
    await call.answer()

@dp.pre_checkout_query_handler(state=PaymentStates.choosing_provider)
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT, state=PaymentStates.choosing_provider)
async def process_payment(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    expiry_date = date.today() + timedelta(days=30)

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, free_uses, premium, tokens_left, last_reset, subscription_expires, full_name)
            VALUES ($1, 3, true, 10000, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
                premium = EXCLUDED.premium,
                subscription_expires = EXCLUDED.subscription_expires,
                full_name = EXCLUDED.full_name
        """, user_id, date.today(), expiry_date, f"{message.from_user.username} {message.from_user.first_name}")

    await message.answer(f"✅ Платеж успешно проведен! Подписка активна до {expiry_date}")
    await state.finish()

# Main bot handlers
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    full_name = f"{message.from_user.username} {message.from_user.first_name}"
    async with pool.acquire() as conn:
        await conn.execute(f"""
            INSERT INTO users (user_id, free_uses, premium, tokens_left, last_reset, full_name)
            VALUES ($1, 3, false, 10000, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, date.today(),full_name)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Начать Чат"), KeyboardButton("Купить Подписку"))
    await message.answer("Добро пожаловать!", reply_markup=kb)

@dp.message_handler(text="Начать Чат")
async def start_chat(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад"))
    await message.answer("Чат начался 🚀", reply_markup=kb)
    await BotStates.selecting_model.set()
    await message.answer("Доступные модели:", reply_markup=await build_models_keyboard(0))

async def build_models_keyboard(page):
    models = await get_online_models()
    keyboard = InlineKeyboardMarkup(row_width=2)

    for model in models[page*10:(page+1)*10]:
        model_name = model.split('/')[-1]
        keyboard.insert(InlineKeyboardButton(model_name, callback_data=f"model_{model}"))

    if page > 0:
        keyboard.row(InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    if len(models) > (page+1)*10:
        keyboard.row(InlineKeyboardButton("Вперед ➡️", callback_data=f"page_{page+1}"))

    return keyboard

@dp.callback_query_handler(lambda c: c.data.startswith('page_'), state=BotStates.selecting_model)
async def process_page(call: types.CallbackQuery, state: FSMContext):
    page = int(call.data.split('_')[1])
    await call.message.edit_reply_markup(await build_models_keyboard(page))

@dp.message_handler(text="Назад", state="*")
async def handle_text_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == BotStates.chatting.state:
        kb = InlineKeyboardMarkup(row_width=2)
        for field in field_prompts:
            kb.insert(InlineKeyboardButton(field, callback_data=f"field_{field}"))
        kb.row(InlineKeyboardButton("Назад", callback_data="back"))
        await message.answer("Выберите режим:", reply_markup=kb)
        await BotStates.selecting_field.set()
    else:
        main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
        main_kb.add(KeyboardButton("Начать Чат"), KeyboardButton("Купить Подписку"))
        await message.answer("Сессия завершена. Для нового запроса нажмите 'Начать Чат'", reply_markup=main_kb)
        await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('model_'), state=BotStates.selecting_model)
async def select_model(call: types.CallbackQuery, state: FSMContext):
    model = call.data.split('model_')[1]
    model_name = model.split('/', 1)[-1].strip()
    if not await check_model_status(model):
        await call.answer("❌ Эта модель временно недоступна", show_alert=True)
        return

    await state.update_data(selected_model=model)
    await BotStates.next()

    kb = InlineKeyboardMarkup(row_width=2)
    for field in field_prompts:
        kb.insert(InlineKeyboardButton(field, callback_data=f"field_{field}"))
    kb.row(InlineKeyboardButton("Назад", callback_data="back"))

    await call.message.edit_text(f"Выбрана модель: {model_name.title()}\nВыберите режим:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == 'back', state='*')
async def handle_back(call: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state == BotStates.selecting_field.state:
        await BotStates.previous()
        await call.message.edit_text("Доступные модели:", reply_markup=await build_models_keyboard(0))
    else:
        await state.finish()
        await call.message.delete()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Начать Чат"), KeyboardButton("Купить Подписку"))
        await message.answer("Добро пожаловать!", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('field_'), state=BotStates.selecting_field)
async def select_field(call: types.CallbackQuery, state: FSMContext):
    field = call.data.split('field_')[1]
    await state.update_data(selected_field=field)
    await BotStates.next()
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Назад"))
    await call.message.edit_text("Режим выбран. Отправьте ваш запрос:")

@dp.message_handler(state=BotStates.chatting)
async def handle_chat(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await bot.send_chat_action(user_id, types.ChatActions.TYPING)
    if not check_rate_limit(message.from_user.id):
        return

    await bot.send_chat_action(user_id, types.ChatActions.TYPING)
    user_data = await state.get_data()
    model = user_data['selected_model']
    field = user_data['selected_field']
    
    await bot.send_chat_action(user_id, types.ChatActions.TYPING)
    user = await get_user(message.from_user.id)
    if user['free_uses'] <= 0 and user['tokens_left'] < 100 and not user['premium']:
        await message.answer("❌ Лимит запросов исчерпан\n ")
        return

    await bot.send_chat_action(user_id, types.ChatActions.TYPING)
    content, total_tokens = get_ai_response(model, message.text + "\nDo not use \,/ in the text or code", field_prompts[field])
    await bot.send_chat_action(user_id, types.ChatActions.TYPING)
    for chunk in split_message(content):
        await bot.send_chat_action(user_id, types.ChatActions.TYPING)
        await safe_send_message(user_id, chunk)

    # Deduct tokens from the user's balance
    new_tokens_left = user['tokens_left']
    new_free_uses = user['free_uses']

    # Deduct tokens only if the user is not a premium user
    if not user['premium']:
        # If total_tokens exceeds the user's tokens_left, set tokens_left to 0
        if total_tokens > user['tokens_left']:
            new_tokens_left = 0
        else:
            new_tokens_left = user['tokens_left'] - total_tokens

        # Deduct free uses if available
        if user['free_uses'] > 0:
            new_free_uses = user['free_uses'] - 1

    # Update user's token balance and free uses
    await update_user(user_id, tokens_left=new_tokens_left, free_uses=new_free_uses)


async def daily_reset():
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET free_uses = 0,
                tokens_left = 5000,
                last_reset = CURRENT_DATE
            WHERE last_reset < CURRENT_DATE
        """)

async def scheduler():
    aioschedule.every().day.at("00:00").do(daily_reset)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(60)

async def on_startup(dp):
    try:
        await bot.set_webhook(url=os.getenv("WEBHOOK_URL"))
        await create_db_pool()
        await init_db()
        asyncio.create_task(scheduler())
        logger.info("Bot started successfully.")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

async def on_shutdown(dp):
    try:
        await bot.delete_webhook()
        await close_db_pool()
        logger.info("Bot shutdown successfully.")
    except Exception as e:
        logger.error(f"Failed to shutdown bot: {e}")
        raise

from aiogram import executor

# Create an ASGI application for Gunicorn
app = executor.start_webhook(
    dispatcher=dp,
    webhook_path="/",
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    skip_updates=True,
    host="0.0.0.0",
    port=int(os.getenv("PORT", 8000)),
)

