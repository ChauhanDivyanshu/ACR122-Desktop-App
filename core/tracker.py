# """
# core/tracker.py — UID Tracker

# Kya karta hai:
#   - Same card dobara scan hone se rokta hai (debounce)
#   - Puri session mein kaunse cards write hue track karta hai
#   - Stats provide karta hai

# Design:
#   - last_uid  : sirf last scanned card — same card remove karne se reset
#   - seen_uids : session ke sare written UIDs — persist karta hai jab tak
#                 NFCWriter object alive hai
# """


# class Tracker:
#     """
#     UID tracking — duplicate writes rokne ke liye.

#     Usage:
#         tracker = Tracker()

#         uid = reader.get_uid()

#         if tracker.is_same(uid):
#             # Same card abhi bhi rakha hai — skip
#             continue

#         if tracker.is_duplicate(uid):
#             # Pehle se write ho chuka — skip
#             continue

#         # Write karo...
#         tracker.update(uid)
#     """

#     def __init__(self):
#         self.last_uid  = None          # Last scanned card ka UID
#         self.seen_uids = set()         # Session mein sare written cards

#     def is_same(self, uid: str) -> bool:
#         """
#         Same card abhi bhi reader pe rakha hai?

#         Jab user card nahi hatata aur dobara scan attempt hota hai.
#         Write loop mein har iteration pe check karo.

#         True → skip, kuch mat karo
#         False → naya card hai, proceed karo
#         """
#         return uid == self.last_uid

#     def is_duplicate(self, uid: str) -> bool:
#         """
#         Yeh card pehle se is session mein write ho chuka hai?

#         Agar user galti se same card dobara tap kare.
#         is_same() ke baad call karo.

#         True → pehle se done, skip
#         False → naya card hai
#         """
#         return uid in self.seen_uids

#     def update(self, uid: str):
#         """
#         Successful write ke baad call karo.
#         last_uid aur seen_uids dono update hote hain.
#         """
#         self.last_uid = uid
#         self.seen_uids.add(uid)

#     def reset_last(self):
#         """
#         Card reader se hat gaya — next card ke liye ready.
#         seen_uids clear NAHI hota — session history maintain rehti hai.

#         Kab call karo:
#           - Card successfully write ho gaya aur user ne hata liya
#           - Write fail hua lekin naya card chahiye
#         """
#         self.last_uid = None

#     def reset_session(self):
#         """
#         Puri session reset karo — dono last_uid aur seen_uids.
#         Kab use karo: naya batch start karna ho
#         """
#         self.last_uid  = None
#         self.seen_uids = set()

#     def get_stats(self) -> dict:
#         """Session stats — kitne unique cards write hue."""
#         return {
#             "written_count": len(self.seen_uids),
#             "last_uid"     : self.last_uid,
#             "all_uids"     : list(self.seen_uids),
#         }

#     def __repr__(self) -> str:
#         return (
#             f"Tracker(written={len(self.seen_uids)}, "
#             f"last={self.last_uid})"
#         )



# core/tracker.py

# core/tracker.py

class Tracker:
    """
    UID tracking — duplicate writes rokne ke liye.

    Usage:
        tracker = Tracker()
        uid = reader.get_uid()

        if tracker.is_same(uid):
            continue       # Same card abhi bhi rakha hai

        if tracker.is_duplicate(uid):
            continue       # Pehle se write ho chuka

        # Write karo
        tracker.update(uid)
    """

    def __init__(self):
        self.last_uid  = None
        self.seen_uids = set()

    def is_same(self, uid: str) -> bool:
        """
        Same card abhi bhi reader pe rakha hai?

        None check zaroori hai:
          None == None → True (wrong!)
          Pehli scan bhi "same" lag sakti thi
        """
        if not uid or not self.last_uid:
            return False
        return uid == self.last_uid

    def is_duplicate(self, uid: str) -> bool:
        """
        Yeh card is session mein pehle write ho chuka hai?
        """
        if not uid:
            return False
        return uid in self.seen_uids

    def update(self, uid: str):
        """
        Successful write ke baad call karo.
        last_uid aur seen_uids dono update hote hain.
        """
        if not uid:
            return
        self.last_uid = uid
        self.seen_uids.add(uid)

    def reset_last(self):
        """
        Card reader se hat gaya → next card ke liye ready.
        seen_uids clear NAHI hota (session history rehti hai).
        """
        self.last_uid = None

    def reset_session(self):
        """
        Puri session reset — naya batch start karna ho.
        """
        self.last_uid  = None
        self.seen_uids = set()

    def get_stats(self) -> dict:
        return {
            "written_count": len(self.seen_uids),
            "last_uid"     : self.last_uid,
            "all_uids"     : list(self.seen_uids),
        }

    def __repr__(self) -> str:
        return (
            f"Tracker("
            f"written={len(self.seen_uids)}, "
            f"last={self.last_uid})"
        )