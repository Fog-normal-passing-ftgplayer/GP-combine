import { useContext, useState } from 'react';
import { Button, Modal } from 'react-bootstrap';
import { NavLink, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AppContext } from '../Contexts/AppContext';
import FormSelect from './FormSelect';
import { saveButtonLabels } from '../Services/Storage';
import { BUTTONS } from '../Data/Buttons';
import './Navigation.scss';
import WebApi from '../Services/WebApi';
import LanguageSelector from './LanguageSelector';

const BOOT_MODES = {
	GAMEPAD: 0,
	WEBCONFIG: 1,
	BOOTSEL: 2,
};

const ROUTE_TITLES = {
	'/': 'home-label',
	'/settings': 'settings-label',
	'/pin-mapping': 'pin-mapping-label',
	'/boot-mode-mapping': 'boot-mode-mapping-label',
	'/peripheral-mapping': 'peripheral-mapping-label',
	'/display-config': 'display-config-label',
	'/add-ons': 'add-ons-label',
	'/macro': 'macro-label',
	'/backup': 'backup-label',
	'/reset-settings': 'resetSettings-label',
};

const Navigation = () => {
	const { buttonLabels, setButtonLabels } = useContext(AppContext);

	const [show, setShow] = useState(false);
	const [isRebooting, setIsRebooting] = useState(null); // null because we want the button to assume untouched state
	const [menuOpen, setMenuOpen] = useState(false);

	const location = useLocation();
	const { t } = useTranslation('');

	const pageTitle = t(
		`Navigation:${ROUTE_TITLES[location.pathname] || 'home-label'}`,
	);

	const closeMenu = () => setMenuOpen(false);

	const handleClose = () => setShow(false);
	const handleShow = () => {
		setIsRebooting(null);
		setShow(true);
	};
	const handleReboot = async (bootMode) => {
		if (isRebooting === false) {
			setShow(false);
			return;
		}
		setIsRebooting(bootMode);
		await WebApi.reboot(bootMode);
		setIsRebooting(-1);
	};

	const updateButtonLabels = (e) => {
		saveButtonLabels(e.target.value);
		setButtonLabels({ buttonLabelType: e.target.value });
	};

	const linkClass = ({ isActive }) =>
		'sidebar-link' + (isActive ? ' active' : '');

	return (
		<>
			<aside className={'app-sidebar' + (menuOpen ? ' open' : '')}>
				<div className="brand-card">
					<NavLink to="/" onClick={closeMenu}>
						<img src="/images/logo.png" alt="GP-Combine" />
					</NavLink>
					<div className="brand-sub">Web Configurator</div>
				</div>

				<nav className="sidebar-nav">
					<div className="nav-section">
						<div className="nav-section-title">
							{t('Navigation:config-label')}
						</div>
						<NavLink to="/" end className={linkClass} onClick={closeMenu}>
							{t('Navigation:home-label')}
						</NavLink>
						<NavLink
							to="/settings"
							className={linkClass}
							onClick={closeMenu}
						>
							{t('Navigation:settings-label')}
						</NavLink>
						<NavLink
							to="/pin-mapping"
							className={linkClass}
							onClick={closeMenu}
						>
							{t('Navigation:pin-mapping-label')}
						</NavLink>
						<NavLink
							to="/boot-mode-mapping"
							className={linkClass}
							onClick={closeMenu}
						>
							{t('Navigation:boot-mode-mapping-label')}
						</NavLink>
						<NavLink
							to="/peripheral-mapping"
							className={linkClass}
							onClick={closeMenu}
						>
							{t('Navigation:peripheral-mapping-label')}
						</NavLink>
						<NavLink
							to="/display-config"
							className={linkClass}
							onClick={closeMenu}
						>
							{t('Navigation:display-config-label')}
						</NavLink>
						<NavLink
							to="/add-ons"
							className={linkClass}
							onClick={closeMenu}
						>
							{t('Navigation:add-ons-label')}
						</NavLink>
						<NavLink to="/macro" className={linkClass} onClick={closeMenu}>
							{t('Navigation:macro-label')}
						</NavLink>
						<NavLink to="/backup" className={linkClass} onClick={closeMenu}>
							{t('Navigation:backup-label')}
						</NavLink>
						<NavLink
							to="/reset-settings"
							className={({ isActive }) =>
								'sidebar-link danger' + (isActive ? ' active' : '')
							}
							onClick={closeMenu}
						>
							{t('Navigation:resetSettings-label')}
						</NavLink>
					</div>

					<div className="nav-section">
						<div className="nav-section-title">
							{t('Navigation:links-label')}
						</div>
						<a
							className="sidebar-link"
							href="https://gp2040-ce.info/"
							target="_blank"
							rel="noreferrer"
						>
							{t('Navigation:docs-label')}
						</a>
						<a
							className="sidebar-link"
							href="https://github.com/OpenStickCommunity/GP2040-CE"
							target="_blank"
							rel="noreferrer"
						>
							{t('Navigation:github-label')}
						</a>
					</div>
				</nav>

				<div className="sidebar-foot">GP-Combine · Web Configurator</div>
			</aside>

			<header className="app-topbar">
				<button
					type="button"
					className="topbar-burger"
					aria-label="Menu"
					onClick={() => setMenuOpen((v) => !v)}
				>
					☰
				</button>
				<div className="topbar-title">{pageTitle}</div>
				<div className="topbar-actions">
					<Button variant="primary" size="sm" onClick={handleShow}>
						{t('Navigation:reboot-label')}
					</Button>
					<LanguageSelector />
					<div className="topbar-button-labels">
						<FormSelect
							name="buttonLabels"
							className="form-select"
							value={buttonLabels.buttonLabelType}
							onChange={updateButtonLabels}
						>
							{Object.keys(BUTTONS).map((b, i) => (
								<option key={`button-label-option-${i}`} value={BUTTONS[b].value}>
									{BUTTONS[b].label}
								</option>
							))}
						</FormSelect>
					</div>
				</div>
			</header>

			{menuOpen && (
				<div className="sidebar-backdrop" onClick={closeMenu} />
			)}

			<Modal show={show} onHide={handleClose}>
				<Modal.Header closeButton>
					<Modal.Title>{t('Navigation:reboot-modal-label')}</Modal.Title>
				</Modal.Header>
				<Modal.Body>
					{isRebooting === -1
						? t('Navigation:reboot-modal-success')
						: t('Navigation:reboot-modal-body')}
				</Modal.Body>
				<Modal.Footer>
					<Button
						variant="secondary"
						onClick={() => handleReboot(BOOT_MODES.BOOTSEL)}
					>
						{isRebooting !== BOOT_MODES.BOOTSEL
							? t('Navigation:reboot-modal-button-bootsel-label')
							: isRebooting
								? t('Navigation:reboot-modal-button-progress-label')
								: t('Navigation:reboot-modal-button-success-label')}
					</Button>
					<Button
						variant="primary"
						onClick={() => handleReboot(BOOT_MODES.WEBCONFIG)}
					>
						{isRebooting !== BOOT_MODES.WEBCONFIG
							? t('Navigation:reboot-modal-button-web-config-label')
							: isRebooting
								? t('Navigation:reboot-modal-button-progress-label')
								: t('Navigation:reboot-modal-button-success-label')}
					</Button>
					<Button
						variant="success"
						onClick={() => handleReboot(BOOT_MODES.GAMEPAD)}
					>
						{isRebooting !== BOOT_MODES.GAMEPAD
							? t('Navigation:reboot-modal-button-controller-label')
							: isRebooting
								? t('Navigation:reboot-modal-button-progress-label')
								: t('Navigation:reboot-modal-button-success-label')}
					</Button>
				</Modal.Footer>
			</Modal>
		</>
	);
};

export default Navigation;
