export const dashboardSummary = {
  organization: 'Harare Health Services',
  framework: 'Zimbabwe Cyber and Data Protection Act',
  currentScore: '61%',
  openFindings: 8,
};

export const sections = [
  {
    id: 'governance',
    title: 'Governance and accountability',
    summary: 'Establish ownership, policies, and oversight for data protection.',
    question: 'How mature is your privacy governance structure?',
  },
  {
    id: 'inventory',
    title: 'Personal data inventory and classification',
    summary: 'Document what data you hold, where it lives, and why it matters.',
    question: 'How complete is your organisation’s personal data inventory?',
  },
  {
    id: 'lawful-processing',
    title: 'Lawful processing and consent',
    summary: 'Confirm lawful bases and consent management practices.',
    question: 'How consistently are lawful processing records maintained?',
  },
];

export const findings = [
  {
    title: 'No formal breach response runbook',
    risk: 'High',
    action: 'Document, approve, and test a breach response procedure with reporting timelines.',
  },
  {
    title: 'Incomplete processor due diligence',
    risk: 'Medium',
    action: 'Create a vendor review checklist and maintain signed data processing terms.',
  },
  {
    title: 'Data subject request logging is inconsistent',
    risk: 'Low',
    action: 'Adopt a central request register and define response SLAs.',
  },
];
