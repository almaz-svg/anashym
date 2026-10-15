import logging
import re


class SensitiveQueryFilter(logging.Filter):
    """Redact credentials in request URLs before Django's development logging."""
    pattern = re.compile(r'([?&](?:token|password|secret|key)=)[^\s&"]+',re.IGNORECASE)

    @classmethod
    def clean(cls,value):
        return cls.pattern.sub(r'\1[REDACTED]',value) if isinstance(value,str) else value

    def filter(self,record):
        record.msg = self.clean(record.msg)
        if isinstance(record.args,tuple):
            record.args = tuple(self.clean(item) for item in record.args)
        elif isinstance(record.args,dict):
            record.args = {key:self.clean(value) for key,value in record.args.items()}
        return True
