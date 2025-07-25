import asyncio
import logging
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ChatInviteLink, LabeledPrice, PreCheckoutQuery, ContentType
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from db import Base, User
from datetime import date, timedelta
from colorama import Fore, Back, Style, init



load_dotenv()

BOT_TOKEN = getenv("BOT_TOKEN")
GROUP_ID = getenv("GROUP_ID")
GROUP_NAME = getenv("GROUP_NAME")
PAYMENT_PROVIDER_TOKEN_TEST = getenv("PAYMENT_PROVIDER_TOKEN_TEST")
POSTGRES_USER = getenv("POSTGRES_USER")
POSTGRES_PASSWORD = getenv("POSTGRES_PASSWORD")
POSTGRES_DB = getenv("POSTGRES_DB")
POSTGRES_HOST = getenv("POSTGRES_HOST")
DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DB}"

SUB_TITLE = "Доступ к группе"
SUB_DESCRIPTION = "Подписка на 30 дней"
SUB_PRICE = 10000 # *0.01

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)



@dp.message(Command(commands=["start", "help"]))
async def show_commands(message: Message):
    commands_kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="/id"),
                KeyboardButton(text="/my_subscription"),
            ],
            [
                KeyboardButton(text="/payment"),
                KeyboardButton(text="/help"),
            ],
        ],
        resize_keyboard=True
    )

    text = (
        f"Здравствуйте, {message.from_user.first_name} 👋\n"
        "Чтобы начать, ознакомтесь со списком команд оплаты и получения справки о текущей подписке:\n\n"
        "/my_subscription — Получить справку о текущем состоянии подписки ℹ️\n"
        f"/payment — Начать оплату и приобрести ссылку на {GROUP_NAME} 💸\n\n"
        "⚠️ Важно: подписка дается на 30 дней, и перестает быть действительной в день истекания срока в 00:00\n\n"
        "Еще:\n"
        "/id — Узнать ID текущего чата или группы\n"
        "/help — Вывести это сообщение"
    )
    await message.answer(text, reply_markup=commands_kb)


@dp.message(Command(commands=["id"]))
async def get_chat_id(message: Message):
    chat_id = message.chat.id
    chat_type = message.chat.type
    await message.reply(f"💬 ID чата: `{chat_id}`\n📦 Тип: `{chat_type}`", parse_mode="Markdown")


@dp.message(Command(commands=["my_subscription"]))
async def show_user_info(message: Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalars().first()
        first_name = message.from_user.first_name

    if user and user.sub_expire_date and user.sub_expire_date > date.today():
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"Дата истекания срока вашей подписки: <b>{user.sub_expire_date}</b>.\n"
                "Если хотите продлить на месяц - можете еще раз воспользоваться командой /payment 💸\n"
                "И получить 10 дней в подарок ! 🧠"
            ),
            parse_mode="HTML"
        )
    else:
        try:
            is_expire_date_valid = user.sub_expire_date
        except:
            is_expire_date_valid = False

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"На данный момент вы не состоите в группе <b>{GROUP_NAME}</b>.\n"
                f"Дата истекания вашей последней подписки - {is_expire_date_valid if is_expire_date_valid else "Вы ни разу не вступали в группу."}\n"
                "Хотите стать частью нашего сообщества и получить весь материал по курсам?\n"
                "Впишите команду /приобрести для оплаты. 💸\n"
                "После успешной оплаты вы получите одноразовую ссылку на группу. ✅"
            ),
            parse_mode="HTML"
        )


@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    first_name = message.from_user.first_name

    async with async_session() as session:
        user_q = select(User).where(User.user_id == user_id)
        result = await session.execute(user_q)
        user = result.scalars().first()

        if user:
            if user.sub_expire_date >= date.today():
                expire_date = user.sub_expire_date + timedelta(days=40)
                query = update(User).where(User.user_id == user_id).values(sub_expire_date=expire_date)

                text = (
                        f"✅ Подписка продлена до {expire_date}!\n"
                        f"Благодарим за то что остаетесь с нами !"
                    )
            else:
                expire_date = date.today() + timedelta(days=30)
                query = update(User).values(sub_expire_date=expire_date)

                text = (
                    f"✅ Подписка офрмлена до {expire_date}!\n"
                    f"Рады видеть вас снова !"
                )
        else:
            expire_date = date.today() + timedelta(days=30)
            query = insert(User).values(user_id=user_id,sub_expire_date=expire_date)

            text = (
                f"✅ Подписка офрмлена до {expire_date}!\n"
                f"Добро пожаловать !"
            )

        try:
            await session.execute(query)
            await session.commit()

            try:
                invite_link: ChatInviteLink = await bot.create_chat_invite_link(
                                chat_id=GROUP_ID,
                                member_limit=1,
                                creates_join_request=False,
                                name=f"Для @{message.from_user.first_name}"
                )
                await message.reply(f"Ваша персональная ссылка:\n{invite_link.invite_link}")
            except Exception as e:
                    await message.reply(f"Ошибка при создании ссылки: {e}")

            await message.answer(text)

        except Exception as e:
            await session.rollback()
            await message.answer("⚠️ Произошла ошибка при сохранении в базу данных или платеже.")
            print(f"DB error: {e}")


@dp.pre_checkout_query(lambda q: True)
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(Command(commands=["payment"]))
async def sub_payment_test(message: Message):
    prices = [
        LabeledPrice(label="Подписка на 30 дней", amount=SUB_PRICE)
    ]

    payload = f"{message.from_user.id}:{message.from_user.username}"
    await message.answer_invoice(
        title="Подписка на группу",
        description=f"Оплата доступа к группе {GROUP_NAME} на 30 дней",
        provider_token=PAYMENT_PROVIDER_TOKEN_TEST,
        currency="USD",
        prices=prices,
        start_parameter="subscription-start",
        payload=payload
    )



async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    await init_models()
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=f"{Fore.GREEN}%(asctime)s{Style.RESET_ALL} | {Fore.BLUE}%(levelname)s{Style.RESET_ALL} | {Fore.YELLOW}%(name)s{Style.RESET_ALL} | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    asyncio.run(main())