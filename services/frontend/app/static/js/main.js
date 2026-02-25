/**
 * CRM Calendar - Main JavaScript
 * Alpine.js components and HTMX configurations
 */

/**
 * Configure HTMX global settings
 */
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Add CSRF token if available
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (csrfToken) {
        evt.detail.headers['X-CSRF-Token'] = csrfToken;
    }
    
    // Add JSON content type for API requests
    if (evt.detail.path.startsWith('/api/')) {
        evt.detail.headers['Content-Type'] = 'application/json';
    }
});

/**
 * Handle HTMX errors globally
 */
document.body.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX Error:', evt.detail);
    showNotification('An error occurred. Please try again.', 'error');
});

/**
 * Show notification toast
 * @param {string} message - Notification message
 * @param {string} type - Notification type (success, error, warning, info)
 */
function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container') || createNotificationContainer();
    
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} flex items-center justify-between shadow-lg`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" class="ml-4 text-lg">&times;</button>
    `;
    
    container.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

/**
 * Create notification container if it doesn't exist
 */
function createNotificationContainer() {
    const container = document.createElement('div');
    container.id = 'notification-container';
    container.className = 'fixed top-4 right-4 z-50 space-y-2 max-w-md';
    document.body.appendChild(container);
    return container;
}

/**
 * Format date for display
 * @param {Date|string} date - Date to format
 * @returns {string} Formatted date string
 */
function formatDate(date) {
    const d = new Date(date);
    return d.toLocaleDateString('en-IE', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

/**
 * Format time for display
 * @param {Date|string} time - Time to format
 * @returns {string} Formatted time string
 */
function formatTime(time) {
    const d = new Date(time);
    return d.toLocaleTimeString('en-IE', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Debounce function for search inputs
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Handle keyboard shortcuts
 */
document.addEventListener('keydown', function(e) {
    // Escape to close modals
    if (e.key === 'Escape') {
        const modal = document.querySelector('#modal-container > *');
        if (modal) {
            document.getElementById('modal-container').innerHTML = '';
        }
    }
    
    // Ctrl/Cmd + N for new job
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        htmx.ajax('GET', '/calendar/job-modal', '#modal-container');
    }
});

/**
 * Initialize the application
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('CRM Calendar initialized');
    
    // Register HTMX extensions if needed
    if (typeof htmx !== 'undefined') {
        htmx.logAll();  // Enable logging for development
    }
});

// Export functions for use in templates
window.showNotification = showNotification;
window.formatDate = formatDate;
window.formatTime = formatTime;
window.debounce = debounce;
