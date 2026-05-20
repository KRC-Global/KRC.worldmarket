"""
KRC World Market — BidNotice & ScrapingRun 모델
외부 발주공고 메타데이터만 저장. KRC 내부 정보 없음.
"""
from datetime import datetime
from . import db


class BidNotice(db.Model):
    __tablename__ = 'bid_notices'

    id = db.Column(db.Integer, primary_key=True)

    # 원천 식별
    source       = db.Column(db.String(50),  nullable=False, index=True)   # worldbank, adb, edcf ...
    source_id    = db.Column(db.String(200), index=True)                    # 원천 고유 ID
    source_url   = db.Column(db.Text,        nullable=False)
    source_hash  = db.Column(db.String(64),  index=True)                    # 내용 변경 감지
    last_seen_at = db.Column(db.DateTime)

    # 공고 기본 정보
    title        = db.Column(db.Text, nullable=False)
    title_ko     = db.Column(db.Text)                                       # 한글 제목 (보조)
    country      = db.Column(db.String(200), index=True)
    region       = db.Column(db.String(100))
    client       = db.Column(db.String(200))                                # 발주기관 (WB, ADB 등 원천)

    # 분야·분류
    sector               = db.Column(db.String(200), index=True)
    notice_type          = db.Column(db.String(150), index=True)
    procurement_method   = db.Column(db.String(200))
    procurement_category = db.Column(db.String(100), index=True)            # Consultant Services 등

    # 프로젝트 정보 (원천 공개 정보)
    project_id      = db.Column(db.String(100), index=True)
    project_name    = db.Column(db.Text)
    project_name_ko = db.Column(db.Text)                                    # 한글 프로젝트명

    # 본문 발췌·한글 요약
    notice_text     = db.Column(db.Text)                                    # 원문 본문/scope 발췌
    notice_text_ko  = db.Column(db.Text)                                    # 한글 번역/요약
    translated_at   = db.Column(db.DateTime)                                # 번역 시각

    # 일정·금액
    posted_date      = db.Column(db.Date, index=True)
    deadline_date    = db.Column(db.Date, index=True)
    deadline         = db.Column(db.String(50))                             # 원문 표기 보존
    amount_value     = db.Column(db.Numeric(18, 2))
    amount_currency  = db.Column(db.String(10))
    contract_value   = db.Column(db.String(100))                            # 원문 표기 보존

    # KRC 분류 (탐색 보조용 — 내부 의사결정 아님)
    krc_tags         = db.Column(db.JSON)                                   # ['농업','관개/배수','컨설팅']
    relevance_score  = db.Column(db.Integer, default=0, index=True)         # 0-100
    relevance_reason = db.Column(db.Text)                                   # 태그 매칭 근거 (내부용)

    # 위치
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)

    # 관리자 검수 상태 (공개 API에서 노출하지 않음)
    admin_status = db.Column(db.String(20), default='review', index=True)
    admin_note   = db.Column(db.Text)
    assigned_to  = db.Column(db.String(100))

    # 내부 대응 상태 (공개 API에서 노출하지 않음)
    status = db.Column(db.String(50), default='new', index=True)

    # 원본
    raw_data   = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('source', 'source_id', name='uq_bid_notice_source_id'),
    )

    def _days_left(self):
        if not self.deadline_date:
            return None
        delta = (self.deadline_date - datetime.utcnow().date()).days
        return delta

    def to_public_dict(self):
        """공개 API 전용 직렬화 — 화이트리스트 방식.
        KRC 내부 정보(adminStatus, assignedTo, status, rawData 등) 제외.
        """
        days_left = self._days_left()
        return {
            'id':                   self.id,
            'source':               self.source,
            'sourceUrl':            self.source_url,
            'title':                self.title,
            'titleKo':              self.title_ko,
            'country':              self.country,
            'region':               self.region,
            'client':               self.client,
            'sector':               self.sector,
            'noticeType':           self.notice_type,
            'procurementCategory':  self.procurement_category,
            'projectId':            self.project_id,
            'projectName':          self.project_name,
            'projectNameKo':        self.project_name_ko,
            'noticeText':           self.notice_text,
            'noticeTextKo':         self.notice_text_ko,
            'postedDate':           str(self.posted_date) if self.posted_date else None,
            'deadlineDate':         str(self.deadline_date) if self.deadline_date else None,
            'daysLeft':             days_left,
            'deadlineStatus':       ('urgent' if days_left is not None and 0 <= days_left <= 7
                                     else 'open' if days_left is not None and days_left > 7
                                     else 'closed' if days_left is not None and days_left < 0
                                     else 'unknown'),
            'amountValue':          float(self.amount_value) if self.amount_value else None,
            'amountCurrency':       self.amount_currency,
            'contractValue':        self.contract_value,
            'krcTags':              self.krc_tags or [],
            'relevanceScore':       self.relevance_score or 0,
            'lat':                  self.lat,
            'lng':                  self.lng,
            'createdAt':            self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
        }

    def to_admin_dict(self):
        """관리자 API 전용 직렬화 — 검수 필드 포함."""
        d = self.to_public_dict()
        d.update({
            'adminStatus':   self.admin_status,
            'adminNote':     self.admin_note,
            'assignedTo':    self.assigned_to,
            'status':        self.status,
            'relevanceReason': self.relevance_reason,
            'sourceId':      self.source_id,
            'sourceHash':    self.source_hash,
            'lastSeenAt':    self.last_seen_at.isoformat() if self.last_seen_at else None,
            'updatedAt':     self.updated_at.strftime('%Y-%m-%d %H:%M') if self.updated_at else None,
        })
        return d


class ScrapingRun(db.Model):
    """수집 실행 이력"""
    __tablename__ = 'scraping_runs'

    id            = db.Column(db.Integer, primary_key=True)
    run_at        = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    total_found   = db.Column(db.Integer, default=0)
    total_created = db.Column(db.Integer, default=0)
    total_updated = db.Column(db.Integer, default=0)
    total_skipped = db.Column(db.Integer, default=0)
    sources       = db.Column(db.JSON)    # [{name, found, created, error}]
    trigger       = db.Column(db.String(20))   # scheduled / manual
    error         = db.Column(db.Text)

    def to_dict(self):
        return {
            'id':           self.id,
            'runAt':        self.run_at.isoformat() if self.run_at else None,
            'totalFound':   self.total_found,
            'totalCreated': self.total_created,
            'totalUpdated': self.total_updated,
            'totalSkipped': self.total_skipped,
            'sources':      self.sources or [],
            'trigger':      self.trigger,
            'error':        self.error,
        }
