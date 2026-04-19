# import pandas as pd


# class CSVHandler:
#     def __init__(self):
#         self.df = None
#         self.file_path = None

#     def load(self, file_path):
#         self.file_path = file_path
#         self.df = pd.read_csv(file_path)
#         print(f"CSV Loaded: {file_path}")
#         print(self.df.head())

#     def validate(self):
#         required_cols = ["id", "name", "url", "lock", "status"]

#         for col in required_cols:
#             if col not in self.df.columns:
#                 raise Exception(f"Missing column: {col}")

#         print("CSV Validation Passed")

#     def get_next_record(self):
#         pending = self.df[self.df["status"] == "pending"]

#         if pending.empty:
#             return None

#         return pending.iloc[0].to_dict()

#     def mark_done(self, record_id):
#         self.df.loc[self.df["id"] == record_id, "status"] = "done"
#         self.save()

#     def save(self):
#         self.df.to_csv(self.file_path, index=False)

import pandas as pd
import threading
from loguru import logger

class CSVHandler:
    def __init__(self):
        self.df = None
        self.file_path = None
        self._lock = threading.Lock()  # ADD: thread safety

    def load(self, file_path):
        self.file_path = file_path
        self.df = pd.read_csv(file_path)
        logger.info(f"CSV loaded: {file_path} — {len(self.df)} rows")

    def validate(self):
        required_cols = ["id", "name", "url", "lock", "status"]
        missing = [c for c in required_cols if c not in self.df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}")  # ValueError, not Exception
        logger.info("CSV validation passed")

    def get_next_record(self):
        with self._lock:  # ADD: thread-safe
            pending = self.df[self.df["status"] == "pending"]
            if pending.empty:
                return None
            row = pending.iloc[0]
            # Mark as 'current' so crash recovery knows where we stopped
            self.df.at[row.name, "status"] = "current"
            return row.to_dict()

    def mark_done(self, record_id):
        with self._lock:
            self.df.loc[self.df["id"] == record_id, "status"] = "done"
            self.save()

    def mark_error(self, record_id, reason=""):  # ADD: error tracking
        with self._lock:
            self.df.loc[self.df["id"] == record_id, "status"] = "error"
            self.df.loc[self.df["id"] == record_id, "error_reason"] = reason
            self.save()
            logger.error(f"Row {record_id} failed: {reason}")

    def restore_session(self):  # ADD: crash recovery
        """App crash ke baad 'current' status wali row se resume karo"""
        current = self.df[self.df["status"] == "current"]
        if not current.empty:
            # current → pending reset karo taaki dobara try ho
            self.df.loc[current.index, "status"] = "pending"
            logger.info(f"Session restored from row {current.index[0]}")

    def save(self):
        self.df.to_csv(self.file_path, index=False)