from aiohttp import ClientSession, ClientResponse
from aiohttp.client_exceptions import ContentTypeError
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass
from bot_init import YOOMONEY_ACCOUNT_NUMBER


class UnresolvedRequestMethod(Exception):
    """Source code: https://github.com/fofmow/aiomoney."""
    ...


class BadResponse(Exception):
    """Source code: https://github.com/fofmow/aiomoney."""
    ...


class Operation(BaseModel):
    """Описание платежной операции
    https://yoomoney.ru/docs/wallet/user-account/operation-history#response-operation

    Source code: https://github.com/fofmow/aiomoney.
    """
    operation_id: str
    status: str
    execution_datetime: datetime = Field(alias="datetime")
    title: str
    pattern_id: Optional[str] = None
    direction: Literal["in"] | Literal["out"]
    amount: float
    label: Optional[str] = None
    operation_type: str = Field(alias="type")


class OperationDetails(BaseModel):
    """Детальная информация об операции из истории
    https://yoomoney.ru/docs/wallet/user-account/operation-details

    Source code: https://github.com/fofmow/aiomoney.
    """
    error: Optional[str] = None
    operation_id: str
    status: str
    pattern_id: Optional[str] = None
    direction: Literal["in"] | Literal["out"]
    amount: int
    amount_due: Optional[int] = None
    fee: Optional[int] = None
    operation_datetime: datetime = Field(alias="datetime")
    title: str
    sender: Optional[int] = None
    recipient: Optional[str] = None
    recipient_type: Optional[str] = None
    message: Optional[str] = None
    comment: Optional[str] = None
    label: Optional[str] = None
    details: Optional[str] = None
    operation_type: str = Field(alias="type")


class BalanceDetails(BaseModel):
    """Source code: https://github.com/fofmow/aiomoney."""
    total: float
    available: float
    deposition_pending: Optional[int] = None
    blocked: Optional[int] = None
    debt: Optional[int] = None
    hold: Optional[int] = None


class LinkedCard(BaseModel):
    """Source code: https://github.com/fofmow/aiomoney."""
    pan_fragment: str
    card_type: str = Field(None, alias="type")


class AccountInfo(BaseModel):
    """Source code: https://github.com/fofmow/aiomoney."""
    account: str  # номер счета
    balance: float  # баланс счета
    currency: str  # код валюты счета
    account_status: str
    account_type: str
    balance_details: Optional[BalanceDetails] = None
    cards_linked: Optional[list[LinkedCard]] = None


@dataclass(frozen=True, slots=True)
class PaymentSource:
    """Source code: https://github.com/fofmow/aiomoney."""
    BANK_CARD = "AC"
    YOOMONEY_WALLET = "PC"


@dataclass(frozen=True, slots=True)
class PaymentForm:
    """Source code: https://github.com/fofmow/aiomoney."""
    link_for_customer: str
    payment_label: str


async def send_request(url: str,
                       method: str = "post",
                       response_without_data: bool = False,
                       **kwargs) -> (ClientResponse, dict | None):
    """Source code: https://github.com/fofmow/aiomoney."""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    if add_headers := kwargs.pop("headers", {}):
        headers |= add_headers

    method = method.lower().strip()
    await check_method(method)

    async with ClientSession() as session:
        async with getattr(session, method)(url, headers=headers, **kwargs) as response:
            await post_handle_response(response)

            if response_without_data:
                return response

            return response, await response.json()

ALLOWED_METHODS = ("post", "get")


async def check_method(method: str):
    """Source code: https://github.com/fofmow/aiomoney."""
    if method not in ALLOWED_METHODS:
        raise UnresolvedRequestMethod


async def post_handle_response(response: ClientResponse):
    """Source code: https://github.com/fofmow/aiomoney."""
    try:
        response_data = await response.json()
        if isinstance(response_data, dict) and response_data.get("error"):
            raise BadResponse(
                f"error — {response_data.get('error')}, response is {response}")

    except ContentTypeError:
        ...

    if response.status >= 400:
        raise BadResponse(response)


class YooMoneyWallet:
    """Source code: https://github.com/fofmow/aiomoney."""

    def __init__(self, access_token: str):
        self.host = "https://yoomoney.ru"
        self.__headers = dict(Authorization=f"Bearer {access_token}")

    async def get_operation_history(self, label: str | None = None) -> list[Operation]:
        """Source code: https://github.com/fofmow/aiomoney."""
        label = str(label)
        history_url = self.host + "/api/operation-history"
        response, data = await send_request(
            history_url, headers=self.__headers
        )
        if operations := data.get("operations"):
            parsed = [Operation.model_validate(
                operation) for operation in operations]
            if label:
                parsed = [
                    operation for operation in parsed if operation.label == label]
            return parsed

    async def create_payment_form(self,
                                  amount_rub: int,
                                  unique_label: str,
                                  success_redirect_url: str | None = None,
                                  payment_source: PaymentSource = PaymentSource.BANK_CARD
                                  ) -> PaymentForm:
        """Source code: https://github.com/fofmow/aiomoney."""
        unique_label = str(unique_label)
        quickpay_url = "https://yoomoney.ru/quickpay/confirm.xml?"
        params = {
            "receiver": YOOMONEY_ACCOUNT_NUMBER,
            "quickpay-form": "button",
            "paymentType": payment_source,
            "sum": amount_rub,
            "successURL": success_redirect_url,
            "label": unique_label
        }
        params = {k: v for k, v in params.items() if v}
        response = await send_request(quickpay_url, response_without_data=True, params=params)

        return PaymentForm(
            link_for_customer=str(response.url),
            payment_label=unique_label
        )

    async def check_payment_on_successful(self, label: str) -> bool:
        """Source code: https://github.com/fofmow/aiomoney."""
        label = str(label)
        need_operations = await self.get_operation_history(label=label)
        return bool(need_operations) and need_operations.pop().status == "success"
