/**
 * Welcome Page Logic
 * Simple animations and interactions for the landing page
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Welcome page loaded');
    
    // Add smooth hover effects (already handled by Tailwind)
    // Additional custom logic can be added here
    
    // Example: Add keyboard shortcut for navigation
    document.addEventListener('keydown', function(e) {
        if (e.key === '1') {
            window.location.href = '/scan';
        } else if (e.key === '2') {
            window.location.href = '/register';
        }
    });
});
