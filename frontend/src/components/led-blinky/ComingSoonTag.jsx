import React from 'react'

const ComingSoonTag = ({ text = 'Coming soon' }) => (
    <span
        style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2px 8px',
            borderRadius: '999px',
            border: '1px solid #9333ea',
            background: '#0a0a0a',
            color: '#d1d5db',
            fontSize: '10px',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
        }}
    >
        {text}
    </span>
)

export default ComingSoonTag
