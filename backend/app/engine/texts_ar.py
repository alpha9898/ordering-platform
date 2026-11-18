"""All customer-facing Arabic text in one place."""

from __future__ import annotations

import re
from decimal import Decimal

STATUS_AR = {
    "placed": "مستني تأكيد المطعم ⏳",
    "accepted": "اتقبل وهيتجهز حالًا 👨‍🍳",
    "preparing": "بيتجهز دلوقتي 🍳",
    "out_for_delivery": "خرج للتوصيل 🛵",
    "ready_for_pickup": "جاهز للاستلام 🎉",
    "completed": "اتسلم ✅",
    "rejected": "اترفض ❌",
    "cancelled": "اتلغى",
}

PAYMENT_AR = {"cod": "كاش عند الاستلام", "wallet": "محفظة / إنستاباي"}

_DIACRITICS = re.compile(r"[ً-ٰٟـ]")  # harakat + tatweel
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(text: str) -> str:
    """Loose Arabic normalization for matching keywords and names."""
    t = _DIACRITICS.sub("", text or "").translate(_ARABIC_DIGITS)
    t = re.sub("[إأآٱ]", "ا", t).replace("ة", "ه").replace("ى", "ي")
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.lower().split())


def price(v: Decimal | float | int) -> str:
    d = Decimal(str(v))
    return f"{d:.0f}" if d == d.to_integral_value() else f"{d:.2f}".rstrip("0")


def egp(v: Decimal | float | int) -> str:
    return f"{price(v)} ج"


CANCEL_WORDS = {"الغاء", "الغي", "cancel", "stop"}
HUMAN_WORDS = {"موظف", "كلم موظف", "عايز موظف", "خدمه العملاء", "human", "agent"}
MENU_WORDS = {"منيو", "المنيو", "القائمه", "menu", "ابدا", "start"}
CART_WORDS = {"سله", "السله", "cart"}
STATUS_WORDS = {"حاله طلبي", "طلبي", "status", "حاله الطلب"}


def greeting(customer_name: str | None, restaurant: str) -> str:
    who = f" يا {customer_name}" if customer_name else ""
    return f"أهلًا بيك{who} في {restaurant} 👋\nاختار القسم اللي تحب تطلب منه 👇"


def closed(restaurant: str, opens: str | None) -> str:
    if opens:
        return f"أهلًا بيك في {restaurant} 👋\nاحنا مقفولين دلوقتي، بنفتح {opens}. مستنيينك!"
    return f"أهلًا بيك في {restaurant} 👋\nاحنا مقفولين دلوقتي. مستنيينك قريب!"


NOT_ACCEPTING = "معلش، المطعم مش بيستقبل طلبات دلوقتي 🙏 جرّب كمان شوية."
UNAVAILABLE = "الخدمة غير متاحة حاليًا."
EMPTY_MENU = "المنيو مش متاح دلوقتي، جرّب كمان شوية 🙏"
CANCELLED = "تمام، اتلغى الطلب ✅\nابعت أي رسالة لما تحب تطلب تاني."
INVALID = "اختار من الاختيارات اللي تحت 👇"
STUCK = "شكلي مش فاهمك 😅 تحب تكلم حد من فريقنا؟"
ITEM_UNAVAILABLE = "الصنف ده مش متاح دلوقتي، اختار حاجة تانية 🙏"
ASK_ADDRESS = "اكتب عنوانك بالتفصيل 🏠\n(المنطقة، الشارع، رقم العمارة، الدور، علامة مميزة)"
ASK_LOCATION = "ابعت موقعك 📍 عشان الدليفري يوصلك بالظبط\nأو اكتب عنوانك بالتفصيل (المنطقة، الشارع، رقم العمارة، الدور، علامة مميزة)"
ASK_DETAILS = "وصلنا موقعك ✅\nاكتب تفاصيل العنوان: رقم العمارة، الدور، الشقة، وأي علامة مميزة 🏠"
DETAILS_SHORT = "اكتب تفاصيل أكتر شوية لو سمحت (رقم العمارة والدور) 🙏"
BAD_LOCATION = "الموقع ده مش واضح، ابعته تاني أو اكتب العنوان 🙏"
ADDRESS_SHORT = "العنوان قصير شوية، اكتبه بالتفصيل لو سمحت 🙏"
NO_ACTIVE_ORDER = "مفيش طلب حالي. ابعت «منيو» عشان تطلب 😊"
CART_EMPTY = "سلتك فاضية."
CART_CLEARED = "فضّينا السلة 🧹"
ADDED = "✅ اتضاف للسلة"
EDITED = "✅ اتعدلت السلة"


def human_requested(restaurant: str) -> str:
    return f"تمام 🙏 حد من فريق {restaurant} هيرد عليك هنا في أقرب وقت."


def order_placed(order_no: int, total, payment: str, wallet_number: str = "") -> str:
    lines = [
        "✅ تم استلام طلبك!",
        f"رقم الطلب: #{order_no}",
        f"الإجمالي: {egp(total)}",
    ]
    if payment == "wallet" and wallet_number:
        lines.append(f"حوّل المبلغ على {wallet_number} وهنأكد الدفع معاك.")
    lines.append("هنبعتلك رسالة أول ما المطعم يأكد الطلب 🙏")
    return "\n".join(lines)


def status_line(order_no: int, status: str) -> str:
    return f"طلبك #{order_no}: {STATUS_AR.get(status, status)}"


def status_notification(order_no: int, status: str, fulfillment: str, eta: int | None, reason: str | None, restaurant: str) -> str | None:
    """Message sent to the customer when staff change an order's status."""
    if status == "accepted":
        when = f" خلال حوالي {eta} دقيقة" if eta else ""
        if fulfillment == "delivery":
            return f"👨‍🍳 تم قبول طلبك #{order_no}، وهيوصلك{when}."
        return f"👨‍🍳 تم قبول طلبك #{order_no}، وهيكون جاهز للاستلام{when}."
    if status == "out_for_delivery":
        return f"🛵 طلبك #{order_no} خرج للتوصيل، هيوصلك قريب!"
    if status == "ready_for_pickup":
        return f"🎉 طلبك #{order_no} جاهز للاستلام من {restaurant}."
    if status == "rejected":
        return f"معلش 🙏 مش هنقدر ننفذ طلبك #{order_no}.\nالسبب: {reason or '-'}"
    if status == "cancelled":
        return f"تم إلغاء طلبك #{order_no}. لو في أي استفسار ابعتلنا «موظف»."
    return None
