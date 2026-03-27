export type ReviewCard = {
  commentId: string
  reviewer: string
  path?: string
  line?: number
  body: string
  classification: 'needs_input' | 'ai_can_fix'
  draftReply: string
  fixPlan?: string
}

type ReviewCommentCardProps = {
  card: ReviewCard
  onDraftAction: (message: string) => void
}

export function ReviewCommentCard({ card, onDraftAction }: ReviewCommentCardProps) {
  const tone = card.classification === 'needs_input' ? 'amber' : 'green'
  const label = card.classification === 'needs_input' ? 'Needs your input' : 'AI can fix'

  return (
    <article className="review-card">
      <div className="review-head">
        <div className="review-head-main">
          <div className="reviewer-pill">
            <span className="review-avatar">{card.reviewer.slice(0, 1).toUpperCase()}</span>
            <span>{card.reviewer}</span>
          </div>
          <span className={`review-tag is-${tone}`}>{label}</span>
        </div>
        <span className="review-path">
          {card.path}
          {card.line ? `:${card.line}` : ''}
        </span>
      </div>

      <div className="review-body">“{card.body}”</div>

      <div className="review-draft-label">{card.classification === 'needs_input' ? 'AI DRAFT REPLY' : 'AI FIX READY'}</div>
      <div className="review-draft">{card.classification === 'needs_input' ? card.draftReply : card.fixPlan || card.draftReply}</div>

      <div className="review-actions">
        {card.classification === 'needs_input' ? (
          <>
            <button type="button" className="button-secondary" onClick={() => onDraftAction(card.draftReply)}>
              Edit reply
            </button>
            <button type="button" className="button-primary" onClick={() => onDraftAction(`Reply to review comment: ${card.draftReply}`)}>
              Post this reply
            </button>
          </>
        ) : (
          <>
            <button type="button" className="button-secondary" onClick={() => onDraftAction(card.fixPlan || card.draftReply)}>
              Edit fix
            </button>
            <button type="button" className="button-green" onClick={() => onDraftAction(`Apply this review fix and reply "Fixed": ${card.fixPlan || card.draftReply}`)}>
              Apply fix + reply
            </button>
          </>
        )}
      </div>
    </article>
  )
}
