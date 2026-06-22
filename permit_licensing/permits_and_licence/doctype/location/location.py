import frappe
from frappe.model.document import Document


class Location(Document):
	def validate(self):
		self.validate_at_least_one_identifier()
		self.validate_single_primary()

	def validate_at_least_one_identifier(self):
		"""At least one of plot_number, makani_number, ejari_reference, address_line_1
		must be populated. Resolves the Building-Permit-early-stage gap: a plot under
		construction may have only a plot_number with no formal address yet."""
		identifiers = [
			self.plot_number,
			self.makani_number,
			self.ejari_reference,
			self.address_line_1,
		]
		if not any(identifiers):
			frappe.throw(
				"At least one of Plot Number, Makani Number, Ejari Reference, "
				"or Address Line 1 must be filled in."
			)

	def validate_single_primary(self):
		"""Only one Location per Business may have is_primary = 1."""
		if not self.is_primary:
			return
		existing = frappe.db.exists(
			"Location",
			{
				"business": self.business,
				"is_primary": 1,
				"name": ["!=", self.name],
			},
		)
		if existing:
			frappe.throw(
				f"Business {self.business} already has a primary Location ({existing}). "
				"Unset the existing primary before marking a new one."
			)
