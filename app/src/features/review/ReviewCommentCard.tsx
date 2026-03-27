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
  const label = card.classification === 'needs_input' ? '需要你决策' : 'AI 可直接修复'

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

      <div className="review-draft-label">{card.classification === 'needs_input' ? 'AI 回复草稿' : 'AI 修复方案'}</div>
      <div className="review-draft">{card.classification === 'needs_input' ? card.draftReply : card.fixPlan || card.draftReply}</div>

      <div className="review-actions">
        {card.classification === 'needs_input' ? (
          <>
            <button type="button" className="button-secondary" onClick={() => onDraftAction(card.draftReply)}>
              编辑回复
            </button>
            <button type="button" className="button-primary" onClick={() => onDraftAction(`回复这条评审评论：${card.draftReply}`)}>
              发送这条回复
            </button>
          </>
        ) : (
          <>
            <button type="button" className="button-secondary" onClick={() => onDraftAction(card.fixPlan || card.draftReply)}>
              编辑修复
            </button>
            <button type="button" className="button-green" onClick={() => onDraftAction(`应用这次评审修复并回复“已修复”：${card.fixPlan || card.draftReply}`)}>
              应用修复并回复
            </button>
          </>
        )}
      </div>
    </article>
  )
}
