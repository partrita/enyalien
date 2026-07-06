(function() {
    let startX = 0;
    let startY = 0;
    let currentX = 0;
    let currentY = 0;
    let isDragging = false;
    
    const SWIPE_THRESHOLD = 80; // Distance in pixels required to trigger swipe
    
    // Initialize event listeners
    function initCardInteractions() {
        const card = document.getElementById('review-card');
        if (!card) return;

        // Reset positions
        startX = 0;
        startY = 0;
        currentX = 0;
        currentY = 0;
        isDragging = false;
        
        // Touch events for mobile swiping
        card.addEventListener('touchstart', handleTouchStart, { passive: true });
        card.addEventListener('touchmove', handleTouchMove, { passive: false });
        card.addEventListener('touchend', handleTouchEnd);
        
        // Double tap or single tap to reveal if card is in front state
        card.addEventListener('click', handleCardClick);
    }

    function handleCardClick(e) {
        const card = document.getElementById('review-card');
        if (!card) return;
        
        const state = card.getAttribute('data-state');
        
        // If clicking on buttons, let the default htmx handler take over
        if (e.target.closest('button') || e.target.closest('a')) {
            return;
        }
        
        // Tap card to reveal if on front side
        if (state === 'front') {
            const showAnswerBtn = document.getElementById('btn-show-answer');
            if (showAnswerBtn) {
                showAnswerBtn.click();
            }
        }
    }

    function handleTouchStart(e) {
        const card = document.getElementById('review-card');
        if (!card) return;
        
        // Only allow swipe if card is flipped (answer side)
        const state = card.getAttribute('data-state');
        if (state !== 'back') return;
        
        const touch = e.touches[0];
        startX = touch.clientX;
        startY = touch.clientY;
        isDragging = true;
        card.classList.add('dragging');
    }

    function handleTouchMove(e) {
        if (!isDragging) return;
        
        const card = document.getElementById('review-card');
        if (!card) return;
        
        const touch = e.touches[0];
        currentX = touch.clientX - startX;
        currentY = touch.clientY - startY;
        
        // Prevent vertical scrolling if user is swipe-dragging horizontally
        if (Math.abs(currentX) > Math.abs(currentY)) {
            e.preventDefault();
        } else {
            // If they are scrolling vertically, cancel drag
            cancelDrag(card);
            return;
        }
        
        // Apply visual transform based on drag position
        const rotate = currentX * 0.08; // Rotate slightly as card is dragged
        const opacity = Math.max(0.4, 1 - Math.abs(currentX) / 300);
        
        card.style.transform = `translate3d(${currentX}px, ${currentY * 0.2}px, 0) rotate(${rotate}deg)`;
        card.style.opacity = opacity;
        
        // Color feedback based on swipe direction
        if (currentX > 0) {
            // Swipe right: Good (green aura border)
            card.style.boxShadow = `0 10px 30px rgba(16, 185, 129, ${Math.min(0.4, Math.abs(currentX) / 150)})`;
        } else {
            // Swipe left: Again (red aura border)
            card.style.boxShadow = `0 10px 30px rgba(239, 68, 68, ${Math.min(0.4, Math.abs(currentX) / 150)})`;
        }
    }

    function handleTouchEnd(e) {
        if (!isDragging) return;
        isDragging = false;
        
        const card = document.getElementById('review-card');
        if (!card) return;
        
        card.classList.remove('dragging');
        
        if (currentX > SWIPE_THRESHOLD) {
            // Swipe Right -> Good
            card.style.transition = 'transform 0.2s ease, opacity 0.2s ease';
            card.style.transform = 'translate3d(150%, 0, 0) rotate(30deg)';
            card.style.opacity = 0;
            
            setTimeout(() => {
                const btnGood = document.getElementById('btn-good');
                if (btnGood) btnGood.click();
            }, 150);
            
        } else if (currentX < -SWIPE_THRESHOLD) {
            // Swipe Left -> Again
            card.style.transition = 'transform 0.2s ease, opacity 0.2s ease';
            card.style.transform = 'translate3d(-150%, 0, 0) rotate(-30deg)';
            card.style.opacity = 0;
            
            setTimeout(() => {
                const btnAgain = document.getElementById('btn-again');
                if (btnAgain) btnAgain.click();
            }, 150);
            
        } else {
            // Reset position
            cancelDrag(card);
        }
    }

    function cancelDrag(card) {
        isDragging = false;
        card.classList.remove('dragging');
        card.style.transform = '';
        card.style.opacity = '';
        card.style.boxShadow = '';
    }

    // Keyboard Shortcuts
    function handleKeyDown(e) {
        const card = document.getElementById('review-card');
        if (!card) return;
        
        const state = card.getAttribute('data-state');
        
        if (state === 'front') {
            if (e.code === 'Space' || e.code === 'Enter') {
                e.preventDefault();
                const showAnswerBtn = document.getElementById('btn-show-answer');
                if (showAnswerBtn) showAnswerBtn.click();
            }
        } else if (state === 'back') {
            if (e.code === 'Space' || e.code === 'Enter') {
                e.preventDefault();
                // Default action on space on flipped card is "Good"
                const btnGood = document.getElementById('btn-good');
                if (btnGood) btnGood.click();
            }
            else if (e.code === 'ArrowLeft') {
                e.preventDefault();
                const btnAgain = document.getElementById('btn-again');
                if (btnAgain) btnAgain.click();
            }
            else if (e.code === 'ArrowRight') {
                e.preventDefault();
                const btnGood = document.getElementById('btn-good');
                if (btnGood) btnGood.click();
            }
        }
    }

    // Initial setup on document load
    document.addEventListener('DOMContentLoaded', () => {
        initCardInteractions();
        window.addEventListener('keydown', handleKeyDown);
    });

    // Reinitialize swipe listener on card swapping (HTMX afterSwap)
    document.body.addEventListener('htmx:afterSwap', (event) => {
        if (event.detail.target.id === 'review-container' || event.detail.target.id === 'review-card') {
            initCardInteractions();
            // Emit custom event to refresh navigation bar badge
            document.body.dispatchEvent(new Event('queue-updated'));
        }
    });

})();
