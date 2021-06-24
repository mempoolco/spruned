#!/usr/bin/env python3

# This entry point is for convenience for Github users.
# On pip installations you should use the pip-installed entry point 'spruned', instead

if __name__ == '__main__':
    import sys
    sys.path.insert(0, './')
    from spruned.app import main
    main()
