# Маркер пакета для группировки тестов core/* (crypto, config, db, ...).
# Без него pytest не сможет импортить тесты как tests.core.test_crypto
# при сборках coverage и в IDE.
