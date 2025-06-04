from aiogram.fsm.state import StatesGroup, State

class EditProfile(StatesGroup):
    nickname = State()
    bio = State()
    skills = State()

class OrderStates(StatesGroup):
    # Состояния при создании заказа
    selecting_executor = State()      # Выбор исполнителя из списка
    waiting_first_message = State()   # Ожидание первого сообщения исполнителю
    
    # Состояния работы с заказом
    active_chat = State()             # Активная переписка по заказу
    viewing_history = State()         # Просмотр истории сообщений
    
    # Состояния изменения статуса
    confirming_cancellation = State()  # Подтверждение отмены
    confirming_completion = State()   # Подтверждение завершения
    
    # Состояния для отзывов
    giving_feedback = State()         # Оставление отзыва
    rating_user = State()             # Оценка пользователя

class ReportStates(StatesGroup):
    waiting_for_reason = State()

class ReviewStates(StatesGroup):
    waiting_for_comment = State()  # Ожидание оценки исполнителя (от заказчика)

class OrderCreationStates(StatesGroup):
    discussing = State()  # Состояние обсуждения заказа
    confirming = State()  # Состояние подтверждения заказа

class BrowsingExecutors(StatesGroup):
    viewing = State()

class ChatState(StatesGroup):
    active = State()  # Добавляем состояние active

class CreateOrder(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_skills = State()
    waiting_for_payment = State()

class EditFutureOrder(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_skills = State()
    waiting_payment = State()

class EditCustomerProfile(StatesGroup):
    nickname = State()