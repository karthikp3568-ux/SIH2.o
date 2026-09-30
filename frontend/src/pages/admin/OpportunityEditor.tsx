import { useState } from 'react'

import { api } from '../../api/client'
import { Button, Card, ErrorState, Notice } from '../../components/ui'
import { useAction } from '../../hooks/useAsync'
import type { Opportunity } from '../../api/types'

const TYPES = ['training', 'apprenticeship', 'job', 'enterprise', 'self_employment']
const EDUCATION = ['', 'none', 'primary', 'class_8', 'class_10', 'class_12', 'iti', 'diploma', 'graduate']
const MOBILITY = ['low', 'medium', 'high']

export function OpportunityEditor({
  opportunity,
  onClose,
  onSaved,
}: {
  opportunity: Opportunity | null
  onClose: () => void
  onSaved: () => void
}) {
  const isNew = opportunity === null
  const [form, setForm] = useState({
    title: opportunity?.title ?? '',
    provider: opportunity?.provider ?? '',
    opportunity_type: opportunity?.opportunity_type ?? 'training',
    description: opportunity?.description ?? '',
    sector: opportunity?.sector ?? '',
    skills_required: (opportunity?.skills_required ?? []).join(', '),
    education_required: opportunity?.education_required ?? '',
    eligibility_notes: opportunity?.eligibility_notes ?? '',
    location_label: opportunity?.location_label ?? '',
    district: opportunity?.district ?? '',
    state: opportunity?.state ?? '',
    pincode: opportunity?.pincode ?? '',
    latitude: opportunity?.latitude?.toString() ?? '',
    longitude: opportunity?.longitude?.toString() ?? '',
    mobility_required: opportunity?.mobility_required ?? 'low',
    seats_total: opportunity?.seats_total?.toString() ?? '',
    seats_available: opportunity?.seats_available?.toString() ?? '',
    stipend_or_income_inr: opportunity?.stipend_or_income_inr?.toString() ?? '',
    source: opportunity?.source ?? '',
    source_url: opportunity?.source_url ?? '',
    status: opportunity?.status ?? 'draft',
    valid_until: opportunity?.valid_until ? opportunity.valid_until.slice(0, 10) : '',
  })

  const update = (key: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [key]: value }))

  const save = useAction(async () => {
    const payload: Record<string, unknown> = {
      title: form.title,
      provider: form.provider,
      opportunity_type: form.opportunity_type,
      description: form.description,
      sector: form.sector || null,
      skills_required: form.skills_required
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean),
      education_required: form.education_required || null,
      eligibility_notes: form.eligibility_notes || null,
      location_label: form.location_label || null,
      district: form.district || null,
      state: form.state || null,
      pincode: form.pincode || null,
      latitude: form.latitude ? Number(form.latitude) : null,
      longitude: form.longitude ? Number(form.longitude) : null,
      mobility_required: form.mobility_required,
      seats_total: form.seats_total ? Number(form.seats_total) : null,
      seats_available: form.seats_available ? Number(form.seats_available) : null,
      stipend_or_income_inr: form.stipend_or_income_inr ? Number(form.stipend_or_income_inr) : null,
      source: form.source,
      source_url: form.source_url || null,
      status: form.status,
      valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
    }

    if (isNew) {
      await api.createOpportunity(payload)
    } else {
      await api.updateOpportunity(opportunity.id, payload)
    }
    onSaved()
    return true
  })

  return (
    <div className="stack">
      <div className="row row--between">
        <h2 style={{ margin: 0 }}>{isNew ? 'Add opportunity' : 'Edit opportunity'}</h2>
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>

      {isNew ? (
        <Notice tone="info">
          <p className="small" style={{ margin: 0 }}>
            New listings are created as <strong>draft</strong> and <strong>unverified</strong>. They
            will not be recommended to anyone until a staff member verifies them against the source.
          </p>
        </Notice>
      ) : null}

      <Card>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            void save.run()
          }}
        >
          <div className="grid grid--2">
            <div className="field">
              <label htmlFor="title">Title *</label>
              <input id="title" value={form.title} onChange={(e) => update('title', e.target.value)} required minLength={3} />
            </div>
            <div className="field">
              <label htmlFor="provider">Provider *</label>
              <input id="provider" value={form.provider} onChange={(e) => update('provider', e.target.value)} required minLength={2} />
            </div>
            <div className="field">
              <label htmlFor="type">Type *</label>
              <select id="type" value={form.opportunity_type} onChange={(e) => update('opportunity_type', e.target.value)}>
                {TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sector">Sector</label>
              <input id="sector" value={form.sector} onChange={(e) => update('sector', e.target.value)} />
            </div>
          </div>

          <div className="field">
            <label htmlFor="description">Description *</label>
            <textarea
              id="description"
              value={form.description}
              onChange={(e) => update('description', e.target.value)}
              required
              minLength={10}
              rows={4}
            />
          </div>

          <div className="field">
            <label htmlFor="skills">Skills required (comma separated)</label>
            <input id="skills" value={form.skills_required} onChange={(e) => update('skills_required', e.target.value)} />
            <p className="field__hint">
              These are matched against the skill taxonomy on save. Anything unrecognised is kept as
              free text but will not contribute to skill matching.
            </p>
          </div>

          <div className="grid grid--2">
            <div className="field">
              <label htmlFor="education">Minimum education</label>
              <select id="education" value={form.education_required} onChange={(e) => update('education_required', e.target.value)}>
                {EDUCATION.map((level) => (
                  <option key={level} value={level}>
                    {level ? level.replace('_', ' ') : 'No requirement'}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="mobility">Travel this needs</label>
              <select id="mobility" value={form.mobility_required} onChange={(e) => update('mobility_required', e.target.value)}>
                {MOBILITY.map((band) => (
                  <option key={band} value={band}>
                    {band}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="field">
            <label htmlFor="eligibility">Eligibility notes</label>
            <textarea id="eligibility" value={form.eligibility_notes} onChange={(e) => update('eligibility_notes', e.target.value)} rows={2} />
          </div>

          <div className="grid grid--3">
            <div className="field">
              <label htmlFor="location">Location label</label>
              <input id="location" value={form.location_label} onChange={(e) => update('location_label', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="district">District</label>
              <input id="district" value={form.district} onChange={(e) => update('district', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="state">State</label>
              <input id="state" value={form.state} onChange={(e) => update('state', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="pincode">PIN code</label>
              <input id="pincode" value={form.pincode} onChange={(e) => update('pincode', e.target.value)} pattern="[1-9][0-9]{5}" />
            </div>
            <div className="field">
              <label htmlFor="lat">Latitude</label>
              <input id="lat" type="number" step="0.000001" value={form.latitude} onChange={(e) => update('latitude', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="lon">Longitude</label>
              <input id="lon" type="number" step="0.000001" value={form.longitude} onChange={(e) => update('longitude', e.target.value)} />
            </div>
          </div>
          <p className="field__hint" style={{ marginTop: '-8px' }}>
            Without coordinates this listing cannot be ranked by distance, and its location factor
            will be scored neutrally rather than favourably.
          </p>

          <div className="grid grid--3">
            <div className="field">
              <label htmlFor="seats-total">Seats total</label>
              <input id="seats-total" type="number" min={0} value={form.seats_total} onChange={(e) => update('seats_total', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="seats-available">Seats available</label>
              <input id="seats-available" type="number" min={0} value={form.seats_available} onChange={(e) => update('seats_available', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="income">Monthly income / stipend (₹)</label>
              <input id="income" type="number" min={0} value={form.stipend_or_income_inr} onChange={(e) => update('stipend_or_income_inr', e.target.value)} />
            </div>
          </div>

          <div className="grid grid--2">
            <div className="field">
              <label htmlFor="source">Source * (where this came from)</label>
              <input id="source" value={form.source} onChange={(e) => update('source', e.target.value)} required minLength={3} />
            </div>
            <div className="field">
              <label htmlFor="source-url">Source link</label>
              <input id="source-url" type="url" value={form.source_url} onChange={(e) => update('source_url', e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="status">Status</label>
              <select id="status" value={form.status} onChange={(e) => update('status', e.target.value)}>
                <option value="draft">draft</option>
                <option value="active">active</option>
                <option value="inactive">inactive</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="valid-until">Valid until</label>
              <input id="valid-until" type="date" value={form.valid_until} onChange={(e) => update('valid_until', e.target.value)} />
            </div>
          </div>

          {save.error ? <ErrorState message={save.error} /> : null}

          <div className="row row--end" style={{ marginTop: 'var(--space-5)' }}>
            <Button variant="secondary" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.pending} icon="💾">
              Save
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
