from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .bid_notice import BidNotice, ScrapingRun

__all__ = ['db', 'BidNotice', 'ScrapingRun']
