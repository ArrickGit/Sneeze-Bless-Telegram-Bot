DEFAULT_RULES = [
    "Wait until the final sneeze in a consecutive sneeze streak before blessing. Early blesses can be punished with /unbless.",
    "Only the first two blessers score. If there is only one valid blesser, only that person gets the point.",
]

HELP_TEXT = """Bless You Sneeze Bot commands:

/bless @first @second [points] - Award points to the first two blessers
/bless @first [points] - Award points to a single blesser
/bless self [points] - Bless yourself using your own Telegram username
/bless self @user [points] - Bless yourself and one more user with the same amount
/blessme - Bless yourself for +5 points
/faaaah - Send the sacred faaah audio
/surprise - Send the mystery audio clip
/bless - Start a guided bless entry
/unbless @user [points] [reason] - Deduct points for breaking the rules
/scoreboard - Show the current rankings
/rules - Show the chat rules
/addrule <text> - Add a new rule (chat admins only)
/removerule <number> - Remove a rule by number (chat admins only)
/cancel - Exit a guided bless or unbless prompt

Examples:
/bless @user1 @user2
/bless @user1
/bless @user1 100000
/bless @user1 @user2 100000
/bless self
/bless self @user2
/bless self @user2 5
/bless self 100000
/blessme
/faaaah
/surprise
/unbless @user1 -2 early blessing during a sneeze streak
/unbless @user1 2 early blessing during a sneeze streak
"""
