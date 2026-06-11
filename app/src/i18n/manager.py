"""Internationalization manager with signal-based live language switching."""
from PySide6.QtCore import QObject, Signal
from . import en, zh


class I18nManager(QObject):
    """Manages UI language strings. Emits `changed` when language switches so
    all UI components can refresh their text."""

    changed = Signal(str)  # new lang code

    _instance = None
    _lang = "en"
    _strings = en.STRINGS

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            QObject.__init__(cls._instance)
        return cls._instance

    @classmethod
    def get(cls, key: str, **kwargs) -> str:
        """Get a localized string by key. Format kwargs are applied."""
        s = cls._strings.get(key, key)
        if kwargs:
            s = s.format(**kwargs)
        return s

    @classmethod
    def tr(cls, key: str, **kwargs) -> str:
        """Alias for get()."""
        return cls.get(key, **kwargs)

    @classmethod
    def set_language(cls, code: str):
        """Switch language. 'en' or 'zh'."""
        if code == cls._lang:
            return
        cls._lang = code
        if code == "zh":
            cls._strings = zh.STRINGS
        else:
            cls._strings = en.STRINGS
        if cls._instance:
            cls._instance.changed.emit(code)

    @classmethod
    def current_language(cls) -> str:
        return cls._lang
