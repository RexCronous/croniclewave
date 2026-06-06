''' Shared data models used throughout the application '''

from enum import Enum
from typing import Final


class AutoplayMode(Enum):
    ''' Enum representing an autoplay mode '''
    NONE: Final[int] = 0
    RANDOM: Final[int] = 1
    SIMILAR: Final[int] = 2


class AudioBalanceMode(Enum):
    ''' Enum representing an audio balancing mode '''
    OFF: Final[int] = 0
    REPLAYGAIN: Final[int] = 1
    DYNAMIC: Final[int] = 2
