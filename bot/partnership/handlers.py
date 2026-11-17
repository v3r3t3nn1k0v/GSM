import logging
from pathlib import Path

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

from .keyboards import (
    PARTNERSHIP_OFFER_CB,
    PartnershipCallback,
    back_to_application_keyboard,
    partnership_keyboard,
    subscribe_keyboard,
)
from .texts import DECLINED_TEXT, OFFER_TEXT, PDF_CAPTION

logger = logging.getLogger(__name__)

PDF_PATH = Path(__file__).resolve().parents[2] / "assets" / "partnership.pdf"
PDF_FILENAME = "Партнерская программа.pdf"

# Telegram кэширует файлы: после первой загрузки отправляем по file_id
_pdf_file_id: str | None = None


async def show_offer(callback: CallbackQuery) -> None:
    """Кнопка «Партнёрская программа» в стартовом меню."""
    await callback.message.edit_text(OFFER_TEXT, reply_markup=partnership_keyboard())
    await callback.answer()


async def offer_answer(
    callback: CallbackQuery, callback_data: PartnershipCallback
) -> None:
    """Ответ да/нет на предложение партнёрской программы."""
    if callback_data.accept:
        await _send_pdf(callback.message)
        await callback.answer()
    else:
        await callback.message.edit_text(
            DECLINED_TEXT, reply_markup=subscribe_keyboard()
        )
        await callback.answer("Спасибо за ответ!")


async def _send_pdf(message: Message) -> None:
    global _pdf_file_id
    document = _pdf_file_id or FSInputFile(PDF_PATH, filename=PDF_FILENAME)
    try:
        sent = await message.answer_document(
            document,
            caption=PDF_CAPTION,
            reply_markup=back_to_application_keyboard(),
        )
    except Exception:
        logger.exception("Не удалось отправить PDF партнёрской программы")
        await message.answer(
            "Не получилось отправить файл 🙁 Попробуйте позже через /start."
        )
        return
    if _pdf_file_id is None and sent.document is not None:
        _pdf_file_id = sent.document.file_id
