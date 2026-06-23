import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class Permit(Document):
	# ------------------------------------------------------------------
	# Frappe lifecycle hooks
	# ------------------------------------------------------------------

	def validate(self):
		self.validate_location_required()
		self.validate_location_belongs_to_business()
		self.check_and_log_status_transition()

	def before_save(self):
		pass  # Reserved for pre-save enrichment (e.g. auto-populate stages from PermitType)

	# ------------------------------------------------------------------
	# Validation helpers
	# ------------------------------------------------------------------

	def validate_location_required(self):
		"""
		v1 business rule: all v1 PermitTypes have requires_location = 1.
		Location field is nullable in schema (v2 mobile-permit hook),
		but blocked here for any PermitType with requires_location = 1.
		"""
		if not self.permit_type:
			return
		requires_location = frappe.db.get_value(
			"Permit Type", self.permit_type, "requires_location"
		)
		if requires_location and not self.location:
			frappe.throw(
				f"Permit Type '{self.permit_type}' requires a Location. "
				"Please link a Location before saving."
			)

	def validate_location_belongs_to_business(self):
		"""
		Prevent linking a Location that belongs to a different Business.
		Catches the identity-collision case from the multi-branch stress test.
		"""
		if not self.location or not self.business:
			return
		location_business = frappe.db.get_value("Location", self.location, "business")
		if location_business != self.business:
			frappe.throw(
				f"Location '{self.location}' belongs to Business '{location_business}', "
				f"not '{self.business}'. Select a Location linked to the correct Business."
			)

	# ------------------------------------------------------------------
	# Stage advancement logic
	# ------------------------------------------------------------------

	def get_current_stage_order(self):
		"""
		Returns the lowest stage_order among stages not yet Completed/Skipped.
		Returns None if all stages are done.
		"""
		pending = [
			row.stage_order
			for row in self.stages
			if row.status not in ("Completed", "Skipped", "Rejected")
		]
		return min(pending) if pending else None

	def all_conditions_met_for_stage(self, stage_definition_name):
		"""
		Returns True if all blocking StageConditions for a given
		stage_reference are Met.
		"""
		blocking = [
			row
			for row in self.stage_conditions
			if row.stage_reference == stage_definition_name and row.blocking_flag
		]
		return all(row.condition_status == "Met" for row in blocking)

	def can_advance_stage(self, stage_order):
		"""
		Returns True if all StageInstances at stage_order are Completed/Skipped
		AND all their blocking conditions are Met.
		Implements the ALL-completion rule for parallel multi-agency stages
		(e.g. Building Permit: DCD + DEWA + RTA must all complete at stage_order=20).
		"""
		group = [row for row in self.stages if row.stage_order == stage_order]
		if not group:
			return False
		for stage_row in group:
			if stage_row.status not in ("Completed", "Skipped"):
				return False
			if not self.all_conditions_met_for_stage(stage_row.stage_definition):
				return False
		return True

	# ------------------------------------------------------------------
	# Transition logging
	# ------------------------------------------------------------------

	def log_transition(self, old_state, new_state, reason=None, stage_reference=None):
		"""
		Appends an immutable audit entry to state_transitions.
		Call this whenever status or a stage status changes.
		Never edit existing log rows — append only.
		"""
		self.append(
			"state_transitions",
			{
				"stage_reference": stage_reference,
				"transition_date": now_datetime(),
				"transitioned_by": frappe.session.user,
				"old_state": old_state,
				"new_state": new_state,
				"reason": reason or "",
			},
		)
		
	def check_and_log_status_transition(self):
		"""
		Wires log_transition() into the save cycle.
		Logs when Permit.status changes compared to the last saved state.
		"""
		if self.is_new():
			return
		# Fetch the currently persisted status from DB before this save
		old_status = frappe.db.get_value(self.doctype, self.name, "status")
		if old_status and old_status != self.status:
			self.log_transition(
				old_state=old_status,
				new_state=self.status,
				reason=f"Status changed from {old_status} to {self.status}",
				stage_reference=None
			)
				
	
