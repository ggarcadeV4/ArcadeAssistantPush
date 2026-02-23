import React from 'react'

/**
 * GunnerAlertBar — Yellow striped glitch-animated warning bar
 * Only rendered when there's an active alert
 */
export default function GunnerAlertBar({ message }) {
    if (!message) return null

    return (
        <section className="gunner-alert">
            <div className="gunner-alert__bg" />
            <div className="gunner-alert__content">
                <svg className="gunner-alert__icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2.5"
                    />
                </svg>
                <span>{message}</span>
            </div>
        </section>
    )
}
