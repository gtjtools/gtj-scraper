from sqlalchemy import Column, String, Text, Integer, DECIMAL, DateTime, Enum, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

class Organization(Base):
  __tablename__ = "organizations"
  __table_args__ = {'schema': 'gtj'}
  
  organization_id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
  name = Column(String(255), nullable=False)
  type = Column(ENUM('BROKER', 'OPERATOR', 'ENTERPRISE', 'INTERNAL', name='type'), nullable=False)
  subscription_tier = Column(ENUM('STARTER', 'PROFESSIONAL', 'ENTERPRISE', 'INTERNAL', 'INACTIVE', name='subscription_tier'), nullable=False)
  created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
  updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
  billing_email = Column(String(255))
  tax_id = Column(String(50))
  address = Column(JSON)
  settings = Column(JSON)

class UserProfile(Base):
	__tablename__ = "user_profiles"
	__table_args__ = {'schema': 'gtj'}

	userprofile_id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
	org_id = Column(UUID(as_uuid=True), ForeignKey("gtj.organizations.organization_id"), nullable=False)
	email = Column(String(255), unique=True, nullable=False)
	role = Column(String(50), nullable=False)  # Assuming ENUM_ROLE is a string
	first_name = Column(String(100), nullable=True)
	last_name = Column(String(100), nullable=True)
	phone = Column(String(20), nullable=True)
	last_login = Column(DateTime(timezone=True), nullable=True)
	is_active = Column(Boolean, nullable=False, default=True)
	created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
	preferences = Column(JSON, nullable=True)
	mfa_enabled = Column(Boolean, nullable=False, default=False)
	user_id = Column(UUID(as_uuid=True), ForeignKey("auth.users.user_id"), nullable=False)
	user_roles = relationship("UserRole", back_populates="user")

class UserRole(Base):
  __tablename__ = "user_roles"
  __table_args__ = {'schema': 'gtj'}

  user_role_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_profile_id = Column(UUID(as_uuid=True), ForeignKey("gtj.user_profiles.userprofile_id"), nullable=False)
  role = Column(ENUM('ADMIN', 'OPERATOR', 'BROKER', 'CLIENT', name='user_role_type'), nullable=False)
  is_active = Column(Boolean, nullable=False, server_default="true")
  created_at = Column(DateTime, nullable=False, server_default="now()")
  user = relationship("UserProfile", back_populates="user_roles")

class Operator(Base):
  __tablename__ = "operators"
  __table_args__ = {'schema': 'gtj'}
  
  operator_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  name = Column(String(255), nullable=False)
  dba_name = Column(String(255), nullable=True)
  certificate_number = Column(String(50), unique=True, nullable=True)
  ops_specs = Column(String, nullable=True)
  base_airport = Column(String(4), nullable=True)
  trust_score = Column(DECIMAL(5, 2), nullable=True)
  trust_score_updated_at = Column(DateTime, nullable=True)
  financial_health_score = Column(DECIMAL(5, 2), nullable=True)
  regulatory_status = Column(ENUM('COMPLIANT', 'WARNING', 'VIOLATION', 'SUSPENDED', name='regulatory_status'), nullable=False)
  is_verified = Column(Boolean, nullable=False, server_default="false")
  created_at = Column(DateTime, nullable=False, server_default="now()")

class Aircraft(Base):
  __tablename__ = "aircraft"
  __table_args__ = {'schema': 'gtj'}

  aircraft_id = Column(UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4)
  tail_number = Column(String(10), unique=True, nullable=False)
  operator_id = Column(UUID(as_uuid=True), ForeignKey("gtj.operators.operator_id"), nullable=False)
  make_model = Column(String(100), nullable=False)
  year = Column(Integer, nullable=True)
  serial_number = Column(String(50), nullable=True)
  aircraft_type = Column(String(50), nullable=True)
  passenger_capacity = Column(Integer, nullable=True)
  range_nautical_miles = Column(Integer, nullable=True)
  cruise_speed_knots = Column(Integer, nullable=True)
  current_status = Column(ENUM('AVAILABLE', 'OCCUPIED', 'MAINTENANCE', 'AOG', 'INACTIVE', name='current_status'), nullable=False, default='AVAILABLE')
  last_maintenance = Column(DateTime, nullable=True)
  next_maintenance_due = Column(DateTime, nullable=True)
  insurance_expiry = Column(DateTime, nullable=True)
  home_base = Column(String(4), nullable=True)
  hourly_rate = Column(DECIMAL(10, 2), nullable=True)
  created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
  #updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)  

class AogEvent(Base):
  __tablename__ = "aog_events"
  __table_args__ = {'schema': 'gtj'}
  
  aog_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  tail_number = Column(String(10), nullable=False)
  aircraft_id = Column(UUID(as_uuid=True), ForeignKey("gtj.aircraft.aircraft_id"), nullable=True)
  airport_code = Column(String(4), nullable=False)
  reported_at = Column(DateTime, nullable=False, server_default="now()")
  reported_by = Column(UUID(as_uuid=True), ForeignKey("gtj.user_profiles.userprofile_id"), nullable=False)
  description = Column(String, nullable=False)
  category = Column(ENUM('category1', 'category2', name='aog_category'), nullable=False)
  severity = Column(ENUM('severity1', 'severity2', name='aog_severity'), nullable=False)
  verification_status = Column(ENUM('UNVERIFIED', 'VERIFIED', name='aog_verification_status'), nullable=False, server_default="UNVERIFIED")
  resolution_time = Column(DateTime, nullable=True)
  resolution_description = Column(String, nullable=True)
  impact_level = Column(ENUM('impact1', 'impact2', name='aog_impact_level'), nullable=False)
  estimated_cost = Column(DECIMAL(10, 2), nullable=True)
  passenger_impact = Column(Integer, nullable=True)
  verification_sources = Column(JSON, nullable=True)
  dispute_reason = Column(String, nullable=True)
  created_at = Column(DateTime, nullable=False, server_default="now()")

class Quote(Base):
  __tablename__ = "quotes"
  __table_args__ = {'schema': 'gtj'}
  
  quote_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  quote_number = Column(String(20), nullable=False, unique=True)
  broker_org_id = Column(UUID(as_uuid=True), ForeignKey("gtj.organizations.organization_id"), nullable=False)
  created_by = Column(UUID(as_uuid=True), ForeignKey("gtj.user_profiles.userprofile_id"), nullable=False)
  client_name = Column(String(255), nullable=False)
  client_email = Column(String(255), nullable=True)
  client_phone = Column(String(20), nullable=True)
  departure_airport = Column(String(4), nullable=False)
  arrival_airport = Column(String(4), nullable=False)
  departure_date = Column(DateTime, nullable=False)
  return_date = Column(DateTime, nullable=True)
  passenger_count = Column(Integer, nullable=False)
  baggage_requirements = Column(String, nullable=True)
  special_requests = Column(String, nullable=True)
  status = Column(ENUM('DRAFT', 'SENT', 'ACCEPTED', 'REJECTED', name='quote_status'), nullable=False, server_default="DRAFT")
  total_amount = Column(DECIMAL(12, 2), nullable=True)
  currency = Column(String(3), nullable=False, server_default="USD")
  valid_until = Column(DateTime, nullable=False)
  sent_at = Column(DateTime, nullable=True)
  viewed_at = Column(DateTime, nullable=True)
  accepted_at = Column(DateTime, nullable=True)
  notes = Column(String, nullable=True)
  created_at = Column(DateTime, nullable=False, server_default="now()")
  updated_at = Column(DateTime, nullable=False, server_default="now()")

class QuoteOption(Base):
  __tablename__ = "quote_options"
  __table_args__ = {'schema': 'gtj'}
  
  quote_option_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  quote_id = Column(UUID(as_uuid=True), ForeignKey("gtj.quotes.quote_id"), nullable=False)
  aircraft_id = Column(UUID(as_uuid=True), ForeignKey("gtj.aircraft.aircraft_id"), nullable=False)
  operator_id = Column(UUID(as_uuid=True), ForeignKey("gtj.operators.operator_id"), nullable=False)
  base_price = Column(DECIMAL(10, 2), nullable=False)
  fuel_cost = Column(DECIMAL(8, 2), nullable=False)
  landing_fees = Column(DECIMAL(6, 2), nullable=False, server_default="0")
  crew_fees = Column(DECIMAL(6, 2), nullable=False, server_default="0")
  catering_cost = Column(DECIMAL(4, 2), nullable=False, server_default="0")
  ground_transport = Column(DECIMAL(4, 2), nullable=False, server_default="0")
  other_fees = Column(DECIMAL(6, 2), nullable=False, server_default="0")
  total_price = Column(DECIMAL(12, 2), nullable=False)
  broker_markup = Column(DECIMAL(6, 2), nullable=False, server_default="0")
  final_price = Column(DECIMAL(12, 2), nullable=False)
  is_recommended = Column(Boolean, nullable=False, server_default="false")
  recommendation_reason = Column(String, nullable=True)
  availability_confirmed = Column(Boolean, nullable=False, server_default="false")
  risk_level = Column(ENUM('LOW', 'MEDIUM', 'HIGH', name='risk_level'), nullable=False)
  trust_score = Column(DECIMAL(5, 2), nullable=False)
  estimated_flight_time = Column(Integer, nullable=False)
  aircraft_features = Column(JSON, nullable=True)
  created_at = Column(DateTime, nullable=False, server_default="now()")

class ComplianceDocument(Base):
  __tablename__ = "compliance_documents"
  __table_args__ = {'schema': 'gtj'}
  
  compliance_document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  quote_id = Column(UUID(as_uuid=True), ForeignKey("gtj.quotes.quote_id"), nullable=False)
  document_type = Column(ENUM('type1', 'type2', name='document_type'), nullable=False)
  file_name = Column(String(255), nullable=False)
  file_path = Column(String(512), nullable=False)
  file_size = Column(Integer, nullable=False)
  mime_type = Column(String(100), nullable=False)
  hash_algorithm = Column(String(20), nullable=False, server_default="SHA256")
  file_hash = Column(String(128), nullable=False)
  timestamp_source = Column(String(50), nullable=False)
  timestamp_hash = Column(String(256), nullable=False)
  signed = Column(Boolean, nullable=False, server_default="false")
  signature_hash = Column(String(256), nullable=True)
  access_level = Column(ENUM('PRIVATE', 'PUBLIC', name='access_level'), nullable=False, server_default="PRIVATE")
  expiry_date = Column(DateTime, nullable=True)
  created_by = Column(UUID(as_uuid=True), ForeignKey("gtj.user_profiles.userprofile_id"), nullable=False)
  viewed_count = Column(Integer, nullable=False, server_default="0")
  last_accessed = Column(DateTime, nullable=True)
  created_at = Column(DateTime, nullable=False, server_default="now()")

class FinancialRecord(Base):
  __tablename__ = "financial_records"
  __table_args__ = {'schema': 'gtj'}
  
  financial_record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  operator_id = Column(UUID(as_uuid=True), ForeignKey("gtj.operators.operator_id"), nullable=False)
  record_type = Column(ENUM('type1', 'type2', name='financial_record_type'), nullable=False)
  source = Column(String(255), nullable=False)
  jurisdiction = Column(String(100), nullable=False)
  filing_date = Column(DateTime, nullable=False)
  amount = Column(DECIMAL(15, 2), nullable=True)
  currency = Column(String(3), nullable=False, server_default="USD")
  status = Column(ENUM('status1', 'status2', name='financial_status'), nullable=False)
  case_number = Column(String(100), nullable=True)
  plaintiff_defendant = Column(String, nullable=True)
  description = Column(String, nullable=True)
  resolution_date = Column(DateTime, nullable=True)
  impact_score = Column(DECIMAL(3, 2), nullable=True)
  raw_data = Column(JSON, nullable=False)
  last_verified = Column(DateTime, nullable=False, server_default="now()")
  created_at = Column(DateTime, nullable=False, server_default="now()")

class Payment(Base):
  __tablename__ = "payments"
  __table_args__ = {'schema': 'gtj'}
  
  payment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  quote_id = Column(UUID(as_uuid=True), ForeignKey("gtj.quotes.quote_id"), nullable=False)
  amount = Column(DECIMAL(12, 2), nullable=False)
  currency = Column(String(3), nullable=False, server_default="USD")
  status = Column(ENUM('PENDING', 'COMPLETED', 'FAILED', name='payment_status'), nullable=False, server_default="PENDING")
  payment_method = Column(ENUM('CARD', 'BANK_TRANSFER', 'OTHER', name='payment_method'), nullable=False)
  stripe_payment_intent = Column(String(255), nullable=True)
  stripe_charge_id = Column(String(255), nullable=True)
  authorization_date = Column(DateTime, nullable=True)
  capture_date = Column(DateTime, nullable=True)
  release_date = Column(DateTime, nullable=True)
  release_conditions = Column(JSON, nullable=False)
  conditions_met = Column(JSON, nullable=True)
  broker_fee = Column(DECIMAL(8, 2), nullable=False, server_default="0")
  platform_fee = Column(DECIMAL(6, 2), nullable=False, server_default="0")
  operator_amount = Column(DECIMAL(12, 2), nullable=False)
  refund_amount = Column(DECIMAL(12, 2), nullable=False, server_default="0")
  dispute_status = Column(ENUM('NONE', 'DISPUTED', 'RESOLVED', name='dispute_status'), nullable=True)
  failure_reason = Column(String, nullable=True)
  risk_score = Column(DECIMAL(3, 2), nullable=True)
  created_at = Column(DateTime, nullable=False, server_default="now()")
  updated_at = Column(DateTime, nullable=False, server_default="now()")

class RiskAssessment(Base):
  __tablename__ = "risk_assessments"
  __table_args__ = {'schema': 'gtj'}
  
  risk_assessment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  quote_option_id = Column(UUID(as_uuid=True), ForeignKey("gtj.quote_options.quote_option_id"), nullable=False)
  overall_risk = Column(ENUM('LOW', 'MEDIUM', 'HIGH', name='risk_level'), nullable=False)
  risk_score = Column(DECIMAL(5, 2), nullable=False)
  weather_risk = Column(DECIMAL(3, 2), nullable=False)
  maintenance_risk = Column(DECIMAL(3, 2), nullable=False)
  operator_risk = Column(DECIMAL(3, 2), nullable=False)
  route_risk = Column(DECIMAL(3, 2), nullable=False)
  aircraft_risk = Column(DECIMAL(3, 2), nullable=False)
  crew_risk = Column(DECIMAL(3, 2), nullable=False)
  seasonal_risk = Column(DECIMAL(3, 2), nullable=False)
  factors = Column(JSON, nullable=False)
  recommendations = Column(JSON, nullable=False)
  assessment_date = Column(DateTime, nullable=False, server_default="now()")
  model_version = Column(String(20), nullable=False)
  confidence_level = Column(DECIMAL(3, 2), nullable=False)
  requires_approval = Column(Boolean, nullable=False, server_default="false")
  approved_by = Column(UUID(as_uuid=True), ForeignKey("gtj.user_profiles.userprofile_id"), nullable=True)
  approval_notes = Column(String, nullable=True)

class TrustScore(Base):
  __tablename__ = "trust_scores"
  __table_args__ = {'schema': 'gtj'}
  
  trust_score_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  operator_id = Column(UUID(as_uuid=True), ForeignKey("gtj.operators.operator_id"), nullable=False)
  overall_score = Column(DECIMAL(5, 2), nullable=False)
  safety_score = Column(DECIMAL(5, 2), nullable=False)
  financial_score = Column(DECIMAL(5, 2), nullable=False)
  regulatory_score = Column(DECIMAL(5, 2), nullable=False)
  aog_score = Column(DECIMAL(5, 2), nullable=False)
  factors = Column(JSON, nullable=False)
  calculated_at = Column(DateTime, nullable=False, server_default="now()")
  version = Column(String(20), nullable=False)
  expires_at = Column(DateTime, nullable=False)
  confidence_level = Column(DECIMAL(3, 2), nullable=False)
