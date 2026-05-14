from datetime import datetime
from typing import List, Literal, Optional, Union
from pydantic import BaseModel


class CollectionItem(BaseModel):
    name: str
    modelStickerThumbnailKey: str
    createdAt: datetime
    floorPriceNanoTons: int
    previousDayFloorPriceNanoTons: Optional[int] = None
    volume: int
    isNew: bool
    isNewDate: Optional[datetime] = None
    cashbackCoef: Optional[float] = None


class OrderActivity(BaseModel):
    id: str
    collectionName: str
    modelName: Optional[str] = None
    backdropName: Optional[str] = None
    symbolName: Optional[str] = None
    createdAt: datetime
    finishedAt: datetime
    endAt: datetime
    priceMinNanoTONs: int
    priceMaxNanoTONs: int
    totalQuantity: int
    completedQuantity: int
    isMine: bool
    isNotificationSeen: bool


class OrderEventActivity(BaseModel):
    type: Literal["order"]
    date: datetime
    order: OrderActivity


class OfferActivity(BaseModel):
    id: str
    createdAt: datetime
    priceNanoTONs: int
    isMine: bool


class SaleIdsResponse(BaseModel):
    ids: List[str]
    prices: List[int]


class OrdersResponse(BaseModel):
    orders: List[OrderActivity]
    cursor: Optional[str] = None


class Gift(BaseModel):
    id: str
    receivedGiftId: str
    exportDate: datetime
    receivedDate: datetime
    giftId: int
    giftAddress: Optional[str] = None
    ownerAddress: Optional[str] = None
    ownerName: Optional[str] = None
    maxUpgradedCount: int
    totalUpgradedCount: int
    backdropColorsExtra: str
    backdropColorsCenterColor: int
    backdropColorsEdgeColor: int
    backdropColorsTextColor: int
    backdropColorsSymbolColor: int
    backdropName: Optional[str] = None
    backdrop: Optional[str] = None
    backdropRarityPerMille: int
    modelExtra: Optional[str] = None
    modelName: Optional[str] = None
    model: Optional[str] = None
    modelRarityPerMille: int
    modelStickerKey: str
    modelStickerEmoji: str
    modelStickerSetId: int
    modelStickerThumbnailKey: str
    symbolExtra: Optional[str] = None
    symbolName: Optional[str] = None
    symbol: Optional[str] = None
    symbolRarityPerMille: int
    symbolStickerKey: str
    symbolStickerEmoji: str
    symbolStickerSetId: int
    symbolStickerThumbnailKey: str
    name: str
    number: int
    extra: Optional[str] = None
    title: str
    isReturned: bool
    returnDate: Optional[datetime] = None
    returnToUserId: Optional[str] = None
    collectionName: str
    collection: Optional[str] = None
    internalId: int
    nextResaleDate: datetime
    nextTransferDate: datetime
    premarketStatus: str
    waitGiftUntil: Optional[datetime] = None
    waitingGiftFromUserId: Optional[str] = None
    waitingGiftFromUser: Optional[str] = None
    unlockDate: datetime


class FeedGift(BaseModel):
    id: str
    amount: int
    type: str
    name: str
    modelName: Optional[str] = None
    modelRarityPerMille: Optional[float] = None
    backdropName: Optional[str] = None
    backdropRarityPerMille: Optional[float] = None
    symbolName: Optional[str] = None
    symbolRarityPerMille: Optional[float] = None


class ContainerGift(BaseModel):
    id: str
    gift_id: Optional[str] = None
    model: Optional[str] = None
    collection: Optional[str] = None
    backdrop: Optional[str] = None
    symbol: Optional[str] = None
    tg_number: Optional[int] = None
    price: Optional[int] = None
    modelRarityPerMille: Optional[float] = None
    backdropRarityPerMille: Optional[float] = None
    symbolRarityPerMille: Optional[float] = None
    floorPriceNanoTONsByCollection: Optional[int] = None
    cursor: Optional[str] = None
