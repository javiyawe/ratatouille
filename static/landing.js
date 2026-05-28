/* ==========================================================================
   Ratatui Landing — Creative Interactions Engine
   Custom Cursor · Magnetic Buttons · Scroll Reveal · Parallax · Typewriter
   ========================================================================== */

(function () {
    'use strict';

    // ========================================================================
    // 1. CUSTOM CURSOR
    // ========================================================================
    const cursor = document.getElementById('cursor');
    let cursorX = 0, cursorY = 0;
    let ringX = 0, ringY = 0;
    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    if (!isTouchDevice && cursor) {
        document.addEventListener('mousemove', (e) => {
            cursorX = e.clientX;
            cursorY = e.clientY;
        }, { passive: true });

        // Smooth ring follow
        function animateCursor() {
            ringX += (cursorX - ringX) * 0.15;
            ringY += (cursorY - ringY) * 0.15;

            const dot = cursor.querySelector('.cursor-dot');
            const ring = cursor.querySelector('.cursor-ring');

            if (dot) {
                dot.style.transform = `translate3d(${cursorX}px, ${cursorY}px, 0)`;
            }
            if (ring) {
                ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0)`;
            }

            requestAnimationFrame(animateCursor);
        }
        animateCursor();

        // Hover detection for interactive elements
        const hoverTargets = 'a, button, .btn, .story-card, .exp-card, [data-magnetic], img';
        document.addEventListener('mouseover', (e) => {
            if (e.target.closest(hoverTargets)) {
                cursor.classList.add('is-hovering');
            }
        }, { passive: true });

        document.addEventListener('mouseout', (e) => {
            if (e.target.closest(hoverTargets)) {
                cursor.classList.remove('is-hovering');
            }
        }, { passive: true });
    } else if (cursor) {
        cursor.style.display = 'none';
    }

    // ========================================================================
    // 2. MAGNETIC BUTTONS
    // ========================================================================
    const magneticEls = document.querySelectorAll('[data-magnetic]');

    if (!isTouchDevice) {
        magneticEls.forEach((el) => {
            el.addEventListener('mousemove', (e) => {
                const rect = el.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;

                el.style.transform = `translate(${x * 0.25}px, ${y * 0.25}px)`;
            }, { passive: true });

            el.addEventListener('mouseleave', () => {
                el.style.transform = '';
                el.style.transition = 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
                setTimeout(() => { el.style.transition = ''; }, 400);
            });
        });
    }

    // ========================================================================
    // 3. SCROLL REVEAL (IntersectionObserver)
    // ========================================================================
    const revealElements = document.querySelectorAll('[data-scroll-reveal]');

    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -60px 0px'
    });

    revealElements.forEach((el) => revealObserver.observe(el));

    // ========================================================================
    // 4. PARALLAX — Subtle depth on scroll
    // ========================================================================
    const parallaxEls = document.querySelectorAll('[data-parallax]');
    let ticking = false;

    function updateParallax() {
        const scrollY = window.scrollY;

        parallaxEls.forEach((el) => {
            const speed = parseFloat(el.dataset.speed) || 0.05;
            const rect = el.getBoundingClientRect();
            const center = rect.top + rect.height / 2;
            const viewCenter = window.innerHeight / 2;
            const offset = (center - viewCenter) * speed;

            el.style.transform = `translateY(${offset}px)`;
        });

        ticking = false;
    }

    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(updateParallax);
            ticking = true;
        }
    }, { passive: true });

    // ========================================================================
    // 5. NAVBAR SCROLL STATE
    // ========================================================================
    const navbar = document.getElementById('navbar');

    if (navbar) {
        window.addEventListener('scroll', () => {
            navbar.classList.toggle('scrolled', window.scrollY > 30);
        }, { passive: true });
    }

    // ========================================================================
    // 6. MOBILE HAMBURGER TOGGLE
    // ========================================================================
    const navToggle = document.getElementById('nav-toggle');
    const navMobile = document.getElementById('nav-mobile');

    if (navToggle && navMobile) {
        navToggle.addEventListener('click', () => {
            const isOpen = navToggle.getAttribute('aria-expanded') === 'true';
            navToggle.setAttribute('aria-expanded', String(!isOpen));
            navToggle.setAttribute('aria-label',
                isOpen ? 'Abrir menú de navegación' : 'Cerrar menú de navegación'
            );
            navMobile.classList.toggle('open', !isOpen);
        });

        // Close on link click
        navMobile.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => {
                navToggle.setAttribute('aria-expanded', 'false');
                navToggle.setAttribute('aria-label', 'Abrir menú de navegación');
                navMobile.classList.remove('open');
            });
        });

        // Close on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && navMobile.classList.contains('open')) {
                navToggle.setAttribute('aria-expanded', 'false');
                navToggle.setAttribute('aria-label', 'Abrir menú de navegación');
                navMobile.classList.remove('open');
                navToggle.focus();
            }
        });
    }

    // ========================================================================
    // 7. SEARCH TYPEWRITER EFFECT
    // ========================================================================
    const typewriterEl = document.getElementById('search-typewriter');

    if (typewriterEl) {
        const phrases = [
            'Cena rápida sin encender el horno',
            'Algo reconfortante para el invierno',
            'Postre fácil con chocolate',
            'Recetas con lo que tengo en la nevera'
        ];

        let phraseIndex = 0;
        let charIndex = 0;
        let isDeleting = false;
        let speed = 60;

        function typewrite() {
            const current = phrases[phraseIndex];

            if (isDeleting) {
                typewriterEl.textContent = current.substring(0, charIndex - 1);
                charIndex--;
                speed = 30;
            } else {
                typewriterEl.textContent = current.substring(0, charIndex + 1);
                charIndex++;
                speed = 60 + Math.random() * 40;
            }

            if (!isDeleting && charIndex === current.length) {
                speed = 2000;
                isDeleting = true;

                // Show search results when phrase completes
                showSearchResults();
            } else if (isDeleting && charIndex === 0) {
                isDeleting = false;
                phraseIndex = (phraseIndex + 1) % phrases.length;
                speed = 400;

                // Hide search results when starting new phrase
                hideSearchResults();
            }

            setTimeout(typewrite, speed);
        }

        // Start after a short delay
        setTimeout(typewrite, 1500);
    }

    // Search results animation
    function showSearchResults() {
        const results = document.querySelectorAll('.search-result-item');
        results.forEach((item, i) => {
            setTimeout(() => {
                item.classList.add('visible');
            }, i * 120);
        });
    }

    function hideSearchResults() {
        const results = document.querySelectorAll('.search-result-item');
        results.forEach((item) => {
            item.classList.remove('visible');
        });
    }

    // ========================================================================
    // 8. SMOOTH SCROLL FOR ANCHOR LINKS
    // ========================================================================
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener('click', (e) => {
            const targetId = anchor.getAttribute('href');
            if (targetId === '#') return;

            const target = document.querySelector(targetId);
            if (target) {
                e.preventDefault();
                const offset = 80; // navbar height
                const top = target.getBoundingClientRect().top + window.scrollY - offset;

                window.scrollTo({
                    top: top,
                    behavior: 'smooth'
                });
            }
        });
    });

    // ========================================================================
    // 9. HERO IMAGE TILT ON MOUSE MOVE (Desktop only)
    // ========================================================================
    const heroFrame = document.querySelector('.hero-img-frame');

    if (heroFrame && !isTouchDevice) {
        const heroSection = document.querySelector('.hero');

        heroSection.addEventListener('mousemove', (e) => {
            const rect = heroSection.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;

            heroFrame.style.transform =
                `perspective(1000px) rotateY(${x * 6}deg) rotateX(${-y * 4}deg)`;
        }, { passive: true });

        heroSection.addEventListener('mouseleave', () => {
            heroFrame.style.transform =
                'perspective(1000px) rotateY(-3deg) rotateX(2deg)';
        });
    }

})();
