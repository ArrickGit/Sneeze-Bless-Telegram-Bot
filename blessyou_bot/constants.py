DEFAULT_RULES = [
    "Wait until the final sneeze in a consecutive sneeze streak before blessing. Early blesses can be punished with /unbless.",
    "Only the first two blessers score. If there is only one valid blesser, only that person gets the point.",
]

HELP_TEXT = """Bless You Sneeze Bot commands:

/bless @first @second - Award 1 point to the first two blessers
/bless @first - Award 1 point to a single blesser
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
/unbless @user1 2 early blessing during a sneeze streak
"""
